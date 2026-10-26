"""Natural Language Generation (NLG) for Weave.

Translates verified, structured factual results and action outcomes into friendly,
natural, and conversational WhatsApp/SMS messages.

Strictly preserves factual accuracy: URLs, build IDs, and project identifiers are
validated against the model's output. If NLG times out, fails, or alters critical facts,
the deterministic fallback copy is delivered immediately without delay.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from pydantic import BaseModel, Field

from ..config import Settings

log = logging.getLogger("genesis.sms.nlg")


class NlgOutput(BaseModel):
    message: str = Field(
        description="The friendly, natural, and conversational message for the user. Never prefix with product names."
    )


SYSTEM_PROMPT = """You are Weave, a friendly and smart AI software builder accessible via WhatsApp, SMS, and web chat.
Your role here is to take a verified, factual result of an action and phrase it as a warm, natural, and helpful conversation.

CRITICAL RULES:
1. NO PRODUCT PREFIX: Never start your message with "Weave:" or "Genesis:". Start directly.
2. TONE: Friendly, relaxed, helpful, conversational, and concise (usually 1-3 sentences).
3. FACTUAL INTEGRITY: You MUST preserve all URLs, download links, preview links, project numbers (#1, #2), and build references (G-XXXXX) EXACTLY as provided in the facts. Do not shorten, alter, or omit them.
4. NO INVENTED CAPABILITIES: Never invent build progress, stages, completion times, or features not stated in the verified facts.
5. NO JARGON OR ROBOTIC MENUS: Avoid rigid bullet lists unless listing projects or options genuinely helps.
6. NO EXCESSIVE EMOJIS: Use at most 1 subtle emoji if appropriate, or none.
7. PLAIN TEXT ONLY: No markdown formatting like bolding or headers unless simple emphasis."""


class NlgPresenter:
    """Conversational presentation layer for deterministic action results."""

    def __init__(self, settings: Settings, ai=None):
        self.s = settings
        self.ai = ai

    def present(
        self,
        kind: str,
        facts: dict[str, Any],
        fallback: str,
        user_query: str = "",
    ) -> str:
        """Turn verified facts into natural language, with immediate deterministic fallback."""
        if not getattr(self.s, "nlg_enabled", True):
            return fallback

        if self.ai is None or not getattr(self.ai, "configured", False):
            return fallback

        # If fallback is empty or too trivial, don't spend a model call
        if not fallback or len(fallback.strip()) < 4:
            return fallback

        timeout = getattr(self.s, "nlg_timeout", 12)
        model = getattr(self.s, "nlg_model", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"

        # Build prompt context
        fact_lines = [f"- {k}: {v}" for k, v in facts.items() if v is not None and str(v).strip()]
        fact_str = "\n".join(fact_lines) if fact_lines else fallback

        prompt = (
            f"Action/Topic: {kind}\n"
            f"User said: {user_query or '(user requested an action)'}\n"
            f"Verified Facts:\n{fact_str}\n\n"
            f"Original deterministic message (reference meaning):\n{fallback}\n\n"
            "Produce a warm, natural rephrasing of these facts for the user."
        )

        box: dict[str, Any] = {}

        def _call():
            try:
                # Use custom schema or structured call
                res, _meta = self.ai._structured(
                    SYSTEM_PROMPT,
                    prompt,
                    NlgOutput,
                    attempts=1,
                    model=model,
                    timeout=timeout,
                )
                box["result"] = res.message
            except BaseException as e:  # noqa: BLE001
                box["error"] = e

        t = threading.Thread(target=_call, name="weave-nlg-present", daemon=True)
        t.start()
        t.join(timeout)

        if t.is_alive():
            log.warning("NLG timeout after %ss for kind=%s; using deterministic fallback", timeout, kind)
            return fallback

        if "error" in box or "result" not in box:
            err = box.get("error")
            log.info("NLG presentation skipped for kind=%s (%s); using fallback", kind, type(err).__name__)
            return fallback

        candidate = str(box["result"]).strip()

        # Clean any accidental product name prefixes
        for prefix in ("Weave: ", "Weave:", "Genesis: ", "Genesis:"):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].lstrip()

        if not candidate:
            return fallback

        # Verify factual integrity: all critical tokens must be preserved
        critical_keys = ("url", "deploy_url", "download_url", "preview_url", "build_ref", "ref", "token")
        for key in critical_keys:
            val = facts.get(key)
            if val and isinstance(val, str) and len(val.strip()) > 3:
                val_clean = val.strip()
                if val_clean not in candidate:
                    log.warning(
                        "NLG output omitted critical fact '%s' (%s); reverting to fallback", key, val_clean[:30]
                    )
                    return fallback

        return candidate

# Genesis unified platform: integration plan

Status: Phase 1 audit complete (2026-10-21). Implementation proceeds in small, reversible stages on the
`unified-website-builder` branch. Nothing is pushed.

## 1. Audit findings

### Genesis (this repository, `Jai2010-Jai/genesis` @ f70b987)

Python 3.12 / FastAPI, single machine. Verified on this Mac:

| Area | Implementation | State |
|---|---|---|
| Twilio SMS + WhatsApp webhook | `genesis/sms/routes.py` (signature check, AccountSid check, MessageSid dedupe, delivery callbacks) | works, tested |
| Conversation engine | `genesis/sms/service.py` (commands, rules in `intent.py`, optional AI "chat brain" in `brain.py`) | works, tested |
| Shared state | `genesis/sms/store.py` SQLite (users, projects, messages, jobs with leases, outbox, download tokens, web sessions) | works, tested |
| Mobile web chat | `genesis/sms/chat.py` + `static/chat/` (PWA, session cookie, CSRF). Uses the same `SmsService` as Twilio | works, tested |
| Voice notes | `genesis/sms/voice.py` local faster-whisper | works, tested with fakes |
| Android pipeline | `genesis/core/jobs.py` Orchestrator: Gemini manifest -> validator -> Gradle `assembleDebug` -> bounded repair -> APK verification | works (README: verified builds), tests use fake Gradle |
| Download links | `/download/<token>`: hashed, expiring (72 h), max 25 uses, bound to user + build | works, tested |
| Cloudflare tunnel | `scripts/genesis_public.sh` (quick tunnel, sets `PUBLIC_BASE_URL` at runtime) | script present; tunnel URL is ephemeral |
| AI provider | `make_ai_client`: `api` (Gemini API, `GEMINI_API_KEY`) or `antigravity` (`agentapi` bridge) | `.env` selects `antigravity`, which is unavailable |

Tests: `pytest -q` gives 234 passed, 1 skipped (the opt-in real-Gradle integration test).
`doctor`: JDK 17, Android SDK 35, licences, and Gradle wrapper are OK. AI backend is MISSING (Antigravity).

AI configuration check (no key printed): `GEMINI_API_KEY` is set and authenticates. Model listing works,
auto-selects `gemini-flash-latest`, and one tiny structured call succeeded. That call took about 170 s,
which suggests transient retries or overload. Treat latency and quota as unverified for full builds.

Secrets and user data that must stay out of Git (already ignored): `.env` (Gemini key, Twilio SID and
token, numbers), `data/` (SQLite with phone numbers and messages, access code, tunnel URL, builds, Gradle
cache), `dist/`.

Antigravity dependencies: `core/antigravity.py` (`AntigravityClient`, `make_ai_client`), `config.py`
(`GENESIS_AI_BACKEND`, `GENESIS_ANTIGRAVITY_*`, doctor check), `__main__.py antigravity-check`,
`server.py` and `sms/cli.py` via `make_ai_client`. No durable state depends on Antigravity conversation
IDs: build records store only the model name and timings.

### `adityapokuri229/weave-compliant`

Empty. One commit, one file, `README.md` containing only `# weave-compliant`. Nothing to integrate.

### `adityapokuri229/weave` (reference implementation chosen by the owner)

Checked out at `~/genesis-integration/weave-ref`, commit `52fb655`. Node 18+ ESM; WhatsApp bot (Baileys),
Electron desktop shell, many unrelated concierge features. The website generator is `src/portfolio/`:

| Module | What it really does |
|---|---|
| `designInspirationResearcher.js` | fetches the minimal.gallery RSS feed, asks Gemini for a topic analysis plus 3 design directions as JSON (fonts, palette, components). **Silently falls back to canned directions** if Gemini fails. |
| `bespokeHtmlGenerator.js` | `generateBespokeHtml`: Gemini writes one complete single-file HTML page (Tailwind CDN, Google Fonts). **Silently returns a canned template** on failure. `redesignBespokeHtml`: rewrites existing HTML from feedback. **Silently returns the unchanged HTML** on failure. |
| `portfolioOrchestrator.js` | research -> optional Google Stitch screen -> 3 variants -> writes files -> screenshot (Firefox) -> **always deploys to Netlify** -> state in `projects.json` keyed by WhatsApp chat. |
| `netlifyDeployer.js` | token deploy via `netlify` CLI (token in argv) and **automatic fallback to anonymous Netlify Drop** (public). |
| `stitchClient.js` | Google Stitch MCP (needs `STITCH_API_KEY`). |
| `../gemini-client.js` | Gemini REST with API key; otherwise falls back to the `agy` CLI and then to Google OAuth tokens sent to Cloud Code endpoints with an Antigravity user agent. |

There is no build step: the output is static HTML. Validation is "contains `<html` and `</html>`".
Importing `gemini-client.js` loads `auth.js` and `config.js`. Those load `dotenv`, copy `.env.example`
into a data directory, and read stored OAuth credentials.

## 2. Architecture

```
Twilio SMS/WhatsApp ─┐                         ┌─ AndroidBuilder  (existing Orchestrator: Gemini -> validator -> Gradle -> APK verify)
Web chat (/chat) ────┼─> SmsService ─> router ─┤
Voice note (Whisper)─┘   (one conversation,    └─ WebsiteBuilder  (Node bridge -> weave research + bespoke HTML -> validate -> preview)
                          one SQLite store)            │
                                 │                     └─ publish (Netlify API, token only, owner approval per publish)
                          SmsWorker (leased jobs) ─> notifications through the same outbox
```

Key decisions:

1. **One store.** `SmsStore` already holds users, projects, conversation, jobs and links for all three
   channels, so it becomes the shared project store. Additive migration: `projects.kind`
   (`android`|`website`, default `android`), `projects.deploy_url`, `projects.deploy_site_id`, and
   `users.pending_question`. Existing rows keep working, and nothing is dropped or rewritten.
2. **Builder interface.** The worker picks the builder from `projects.kind`. The Android path is the
   existing Orchestrator, unchanged. The website path is a new `genesis/web/` package with its own build
   records (`data/sites/<id>/`), kept separate from Gradle workspaces.
3. **Reuse weave through a process boundary, not a copy.** `genesis/web/bridge.mjs` imports weave's
   `researchDesignInspirations`, `generateBespokeHtml` and `redesignBespokeHtml` from
   `GENESIS_WEBSITE_ENGINE_DIR`. The bridge:
   - resolves `dotenv` to a no-op stub, so weave's `.env` is never read;
   - points `WEAVE_DATA_DIR` at an empty sandbox, so there are no stored OAuth tokens;
   - wraps weave's Gemini client so only the API-key path can run, which blocks the `agy`, OAuth and
     Cloud Code fallbacks;
   - records every Gemini call, so canned fallbacks are detected and reported as failures rather than
     as successes.

   The orchestrator, Stitch, screenshots and `netlifyDeployer` are deliberately not used (see section 1).
4. **Publishing is explicit.** It is off unless `GENESIS_WEBSITE_DEPLOY=netlify` and `NETLIFY_AUTH_TOKEN`
   are set. Only the owner can publish. Genesis asks first, and nothing happens until the owner replies
   `PUBLISH`. It deploys through the Netlify API with the token in a header only. There is never an
   anonymous fallback.
5. **Delivery.** Android keeps the existing token-protected APK link. Websites get a token-protected
   preview link (`/preview/<token>/`) served with a CSP `sandbox` (opaque origin, so generated scripts
   cannot reach Genesis cookies or APIs), and the actual Netlify URL only after a publish succeeds.
   Messages say "local preview" or "published" accurately.
6. **Routing.** The rules gain website detection and "Android app or website?" clarification, plus
   "what are you building?" as a status question. The chat brain gains `new_website` and `publish`
   actions. Every action still goes through the service's checks (ownership, one job at a time, quotas).
   When the website builder is unavailable, both the rules and the brain say so and start nothing.
7. **AI provider.** `make_ai_client` stays the single switch. Missing keys give clear errors (existing).
   The website builder requires the Gemini API backend and never switches provider. The local `.env` is
   switched from `antigravity` to `api`, a one-line reversible change.

Job states. The store keeps `queued|running|succeeded|failed|cancelled`. Fine-grained stages
(`generating`, `validating`, `building`, `repairing`, `verifying`) live in each build record and drive
progress messages. They are real stage transitions, not percentages.

## 3. Risks

- Gemini latency and quota on this key (the 170 s test call). Bounded by bridge and Gradle timeouts and
  reported truthfully.
- Generated HTML is untrusted and loads third-party CDNs (Tailwind, Google Fonts). Mitigations: served
  sandboxed, size limits, a script-source allowlist in validation and CSP, and never executed on the host.
- weave's prompts are tuned for "portfolio/brand landing pages". Websites are single-page static sites
  with no backend, forms that submit nowhere, and no multi-page sites.
- Netlify publishing cannot be verified without a token (none is configured).
- The quick Cloudflare tunnel URL changes on every restart, so Twilio's webhook must be updated each time.

## 4. Testing strategy

- Unit and service tests with fake AI, fake Gradle and a fake website bridge: routing, clarification,
  ownership, duplicates, concurrency gate, provider failures, rollback, preview CSP, publish approval,
  redaction.
- A bridge contract test that runs the real `bridge.mjs` with a stubbed Gemini module (no network).
- Real end-to-end runs, when the key and quota allow: one website generation and modification, and one
  Android build, through `sms-simulate` with the `log` provider. Real Twilio sends need the owner's
  approval.

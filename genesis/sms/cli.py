"""`python -m genesis sms-*` commands."""

from __future__ import annotations

import signal
import threading
import time
import uuid

from ..config import settings
from .phone import mask


def _components(provider=None):
    from ..core.antigravity import make_ai_client
    from ..core.jobs import Orchestrator
    from .provider import make_provider
    from .service import SmsService
    from .store import SmsStore
    from .worker import SmsWorker

    from ..web.builder import WebsiteBuilder

    ai = make_ai_client(settings)
    orch = Orchestrator(settings, ai)
    store = SmsStore(settings.sms_db_path)
    service = SmsService(settings, store, orch.store)
    service.web = WebsiteBuilder(settings, model_resolver=ai.model_name if settings.ai_backend == "api" else None)
    worker = SmsWorker(settings, store, orch, provider or make_provider(settings), service)
    return store, service, worker


def run_sms_command(args) -> int:
    if args.cmd == "sms-link-code":
        from .store import SmsStore

        hours = max(0.05, min(72.0, args.hours))
        code = SmsStore(settings.sms_db_path).create_link_code(args.role, ttl_s=int(hours * 3600))
        print(f"One-time link code (valid {hours:g} h): {code}")
        print(f"  WhatsApp/SMS: text  LINK {code}")
        if settings.public_base_url:
            print(f"  Web chat:     open  {settings.public_base_url}/chat#code={code}")
        return 0
    if args.cmd == "sms-check":
        return _check()
    if args.cmd == "sms-whatsapp-template":
        return _whatsapp_template()
    if args.cmd == "sms-worker":
        if settings.sms_provider == "off":
            print("Messaging is switched off (GENESIS_SMS_PROVIDER=off)")
            return 1
        _, _, worker = _components()
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        worker.start()
        print(f"SMS worker {worker.worker_id} running (provider {worker.provider.name}). Ctrl+C to stop.")
        stop.wait()
        worker.stop()
        return 0
    if args.cmd == "sms-simulate":
        from .provider import LogProvider
        from .service import Inbound

        provider = LogProvider(settings)
        store, service, worker = _components(provider)
        sid = "SM" + uuid.uuid4().hex
        outcome = service.handle(Inbound(from_=args.sender, to=settings.twilio_phone_number, body=args.text, sid=sid))
        print(f"inbound from {mask(args.sender)} -> {outcome}")
        started = time.monotonic()
        worker.drain()
        for to, body in provider.sent:
            print(f"\n--- SMS to {mask(to)} ---\n{body}")
        print(f"\n(done in {time.monotonic() - started:.0f}s; nothing was sent over SMS, see {provider.path})")
        return 0
    return 2


def _whatsapp_template() -> int:
    """Create (or find) a Content template whose body is {{1}} so Genesis replies can be sent as templates."""
    import json

    from twilio.base.exceptions import TwilioException
    from twilio.rest import Client

    s = settings
    client = Client(s.twilio_account_sid, s.twilio_auth_token, region=s.twilio_region or None, edge=s.twilio_edge or None)
    try:
        for c in client.content.v1.contents.list(limit=200):
            if c.friendly_name == "genesis_reply":
                print(f"Template exists. Put this in .env:\nTWILIO_WHATSAPP_CONTENT_SID={c.sid}")
                return 0
        resp = client.request("POST", "https://content.twilio.com/v1/Content", headers={"Content-Type": "application/json"},
                              data=json.dumps({"friendly_name": "genesis_reply", "language": "en",
                                               "variables": {"1": "Genesis reply"},
                                               "types": {"twilio/text": {"body": "{{1}}"}}}))
    except TwilioException as e:
        detail = str(e.args[1].text if len(e.args) > 1 and hasattr(e.args[1], "text") else e)
        if "20003" in detail or "Trial" in detail:
            print("Twilio refused: the Content API is not available on a Trial account. Upgrade the account first.")
            return 1
        print(f"Twilio error: {detail[:300]}")
        return 1
    if resp.status_code >= 300:
        print(f"Twilio error {resp.status_code}: {resp.text[:300]}")
        return 1
    sid = json.loads(resp.text)["sid"]
    print(f"Created. Put this in .env and restart Genesis:\nTWILIO_WHATSAPP_CONTENT_SID={sid}")
    return 0


def _check() -> int:
    s = settings
    ok = True
    print(f"Provider: {s.sms_provider}   signup: {s.sms_signup}   worker: {s.sms_worker}")
    for issue in s.sms_issues():
        ok = False
        print(f"MISSING  {issue}")
    print(f"Owner numbers: {', '.join(mask(n) for n in s.sms_owner_numbers) or '(none)'}")
    webhook = f"{s.public_base_url}/api/webhooks/twilio/sms" if s.public_base_url else None
    print(f"Inbound webhook (POST): {webhook or '(set PUBLIC_BASE_URL)'}")
    if s.sms_provider != "twilio" or not (s.twilio_account_sid and s.twilio_auth_token):
        return 0 if ok else 1
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    client = Client(s.twilio_account_sid, s.twilio_auth_token, region=s.twilio_region or None, edge=s.twilio_edge or None)
    try:
        acct = client.api.v2010.accounts(s.twilio_account_sid).fetch()
    except TwilioRestException as e:
        print(f"MISSING  Twilio credentials rejected ({e.status} {e.code})")
        return 1
    print(f"Twilio account: status={acct.status} type={acct.type}")
    if acct.type == "Trial":
        ok = False
        print("WARNING  Trial account: SMS only reach Verified Caller IDs and start with 'Sent from your Twilio trial "
              "account'. Upgrade the account for real users.")
    if s.twilio_channel == "whatsapp":
        print(f"Channel: WhatsApp from whatsapp:{s.twilio_phone_number or '(Messaging Service)'}. Set the sender's "
              f"'When a message comes in' webhook to {webhook} (POST) in the Twilio Console (WhatsApp senders/sandbox).")
        print("READY (WhatsApp sender ownership is not checked)" if ok else "NOT READY")
        return 0 if ok else 1
    numbers = client.incoming_phone_numbers.list(limit=50)
    if not numbers:
        ok = False
        print("MISSING  This account owns no phone numbers. Buy an SMS-capable number in the Twilio Console.")
    for n in numbers:
        mine = n.phone_number == s.twilio_phone_number
        caps = n.capabilities or {}
        print(f"{'*' if mine else ' '} {n.phone_number}  sms={caps.get('sms')}  sms_url={n.sms_url or '-'} ({n.sms_method})")
        if mine:
            if not caps.get("sms"):
                ok = False
                print("MISSING  TWILIO_PHONE_NUMBER is not SMS-capable")
            if webhook and (n.sms_url != webhook or (n.sms_method or "").upper() != "POST"):
                ok = False
                print(f"MISSING  Set this number's 'A message comes in' webhook to {webhook} (HTTP POST)")
    if s.twilio_phone_number and s.twilio_phone_number not in {n.phone_number for n in numbers}:
        ok = False
        print("MISSING  TWILIO_PHONE_NUMBER is not a number on this account")
    try:
        verified = client.outgoing_caller_ids.list(limit=50)
        print(f"Verified caller IDs: {', '.join(mask(v.phone_number) for v in verified) or '(none)'}")
    except TwilioRestException:
        pass
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1

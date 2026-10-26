"""CLI: `python -m genesis [serve|doctor|build "<description>"]`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genesis", description="Describe an Android app, get an APK.")
    sub = parser.add_subparsers(dest="cmd")
    sv = sub.add_parser("serve", help="Start the dashboard (default)")
    sv.add_argument("--lan", action="store_true",
                    help="Also accept the Genesis phone app over your Wi-Fi (access code required)")
    sub.add_parser("doctor", help="Check prerequisites")
    sub.add_parser("antigravity-check", help="Send a tiny and a full-size test request through the Antigravity bridge")
    b = sub.add_parser("build", help="Generate and build one app from the command line")
    b.add_argument("prompt")
    b.add_argument("--name", default=None)
    sub.add_parser("sms-worker", help="Run the SMS build worker as its own process (set GENESIS_SMS_WORKER=external)")
    sub.add_parser("sms-whatsapp-template",
                   help="Create the {{1}} WhatsApp Content template (needs a non-trial Twilio account)")
    sub.add_parser("sms-check", help="Check SMS configuration and the Twilio number (read-only, sends nothing)")
    lc = sub.add_parser("sms-link-code", help="Create a one-time code a phone texts as LINK <code>")
    lc.add_argument("--role", choices=["member", "owner"], default="member")
    lc.add_argument("--hours", type=float, default=0.25, help="How long the code stays valid (max 72)")
    sim = sub.add_parser("sms-simulate", help="Feed a text through the SMS flow locally; replies are printed, not sent")
    sim.add_argument("--from", dest="sender", required=True, help="Sender number in E.164, e.g. +919876543210")
    sim.add_argument("text")
    args = parser.parse_args(argv)
    args.cmd = args.cmd or "serve"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "doctor":
        report = settings.doctor()
        for c in report["checks"]:
            print(f"{'OK ' if c['ok'] else 'MISSING'}  {c['name']}: {c['detail']}" + (f"\n         fix: {c['fix']}" if c["fix"] else ""))
        if settings.gemini_api_key or settings.ai_backend == "antigravity":
            from .core.antigravity import make_ai_client
            from .core.gemini import GeminiError
            try:
                print(f"OK       AI model: {make_ai_client(settings).model_name()}")
            except GeminiError as e:
                print(f"MISSING  Gemini: {e}")
                return 1
        from .web.builder import probe

        for c in settings.website_doctor():
            print(f"{'OK ' if c['ok'] else 'MISSING'}  {c['name']}: {c['detail']}")
        if not settings.website_problem():
            ok, detail = probe(settings)
            print(f"{'OK ' if ok else 'FAILED '}  Website engine load: {detail}")
        return 0 if report["ready"] else 1

    if args.cmd == "antigravity-check":
        from .core.antigravity import diagnose
        return diagnose(settings)

    if args.cmd == "build":
        from .core.antigravity import make_ai_client
        from .core.jobs import Orchestrator, public_job
        from .core.schemas import BuildRequest

        orch = Orchestrator(settings, make_ai_client(settings))
        job = orch.run_sync(BuildRequest(prompt=args.prompt, app_name=args.name))
        print(json.dumps(public_job(job), indent=2))
        if job["status"] == "succeeded":
            print(f"\nAPK: {orch.store.path(job['id']) / 'artifact' / job['apk']['filename']}")
        print(f"Log: {orch.store.log_path(job['id'])}")
        return 0 if job["status"] == "succeeded" else 1

    if args.cmd.startswith("sms-"):
        from .sms.cli import run_sms_command

        return run_sms_command(args)

    import uvicorn

    from . import auth

    lan = getattr(args, "lan", False) or settings.host not in ("127.0.0.1", "localhost", "::1")
    if lan:
        settings.host = "0.0.0.0" if settings.host in ("127.0.0.1", "localhost", "::1") else settings.host
    from .server import create_app

    app = create_app()
    print(f"\n  Genesis dashboard:  http://127.0.0.1:{settings.port}")
    if lan:
        code = auth.load_or_create_code(settings.data_dir)
        for ip in auth.lan_addresses():
            print(f"  Phone app server:   http://{ip}:{settings.port}")
        print(f"  Phone access code:  {code}")
        print("  (Open the dashboard and click 'Connect phone' for a QR code. Use only on a trusted network.)\n")
    else:
        print("  Phone app: restart with `python -m genesis serve --lan` to connect over Wi-Fi.\n")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())

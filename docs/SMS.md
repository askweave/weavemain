# Genesis by message: WhatsApp, SMS and mobile web chat

Text Genesis an app idea, get progress updates, request changes, and receive a download link for the
verified APK, without opening the dashboard. Texts go through the **same** Orchestrator the dashboard uses:
Gemini generation → validator → isolated workspace → Gradle → bounded AI repair → APK verification.

## Quick start (phone, today)

```bash
scripts/genesis_public.sh                                   # HTTPS tunnel + Genesis; prints the public URL
.venv/bin/python -m genesis sms-link-code --hours 24        # prints a /chat#code=... link
```

Open the printed `/chat#code=…` link on your phone (it signs you in), tap **Add to Home screen**, and chat. It's
the same conversation engine, commands and build pipeline as WhatsApp/SMS. The quick tunnel URL changes every time
the script starts; use a named Cloudflare tunnel (or any HTTPS reverse proxy) and set `PUBLIC_BASE_URL` for a
stable address.

## Channels

| Channel | Status | Needs |
|---|---|---|
| **Web chat** (`/chat`, installable PWA) | works now | the tunnel script |
| **WhatsApp** (Twilio) | code ready, sandbox sender configured | Console: activate the Sandbox, set its inbound webhook, `join` from the phone; account funds for sending |
| **SMS** (Twilio) | code ready | an SMS number (none on the account); one-way only to Indian mobiles |

Replies go back on the channel the user last wrote in. `TWILIO_WHATSAPP_NUMBER` sets the WhatsApp sender and
`TWILIO_PHONE_NUMBER` the SMS sender. Web chat replies never leave the machine.

## Architecture

```
phone ──SMS──► Twilio ──POST (form, X-Twilio-Signature)──► https://PUBLIC_BASE_URL/api/webhooks/twilio/sms
                                                              │  (tunnel / reverse proxy → 127.0.0.1:8765)
                                                              ▼
                                      genesis/sms/routes.py   validate signature + AccountSid, parse form
                                      genesis/sms/service.py  dedupe MessageSid, identity, rate limits, commands
                                                              │  writes SQLite only, answers in milliseconds
                                                              ▼  with empty TwiML
                                      data/sms.sqlite3        users · projects · messages(in/outbox) · jobs · tokens
                                                              ▲
                     genesis/sms/worker.py (embedded thread or `python -m genesis sms-worker`)
                       job loop: claim (lease) → Orchestrator.create_job/run_existing (shared build slots)
                                 → stage listener → rate-limited progress SMS → success link / failure reason
                       outbox loop: Twilio REST messages.create (retries, status callbacks)
                                                              │
phone ◄──SMS── Twilio ◄───────────────────────────────────────┘
phone ──HTTPS GET /download/<token>──► expiring, hashed, per-build token → the verified APK
```

- **Same engine.** `Orchestrator.create_job()` + `run_existing()` run SMS builds through the existing
  pipeline. Builds are stored in `data/builds/<id>/` like dashboard builds, so they appear in dashboard History
  with their full logs (`source: "sms"`). Dashboard and SMS builds share one Gradle slot limit
  (`GENESIS_MAX_CONCURRENT_BUILDS`).
- **Follow-up changes.** A change build (`base_job_id`) sends the previous version's Kotlin sources plus the
  change request to Gemini (`GeminiClient.modify_app`). The result goes through the same validation, build,
  repair and verification steps. The package ID is kept, so the new APK installs as an update. The manifest
  now has a validated `theme_mode` (system/light/dark) that the server writes into the protected theme, so
  "make it dark" works. If the previous build failed, Genesis rebuilds from the full project description
  (original request + all changes).
- **Durable queue.** SQLite (WAL) with leases. Each job has a reference (`G-7K3PX`), persistent state,
  bounded attempts (`GENESIS_SMS_JOB_MAX_ATTEMPTS`) and exponential backoff (30s, 60s, 120s...). Only
  infrastructure errors are retried (AI overload, worker or server restart, internal errors); real build
  failures are not. A crashed worker's lease expires after 2 minutes and the job is re-queued. Each user
  runs one build at a time. The queue is capped (`GENESIS_SMS_MAX_QUEUED`). Cancellation stops Gradle's
  whole process group. Redis isn't needed: Genesis is a single-machine app with one Android toolchain.
- **Provider abstraction.** `genesis/sms/provider.py` defines `SmsProvider` (`send`, `validate_request`).
  Twilio SMS, Twilio WhatsApp (`TWILIO_CHANNEL=whatsapp`) and a local `log` provider are included. Another
  gateway (for example an Indian DLT-registered provider) is one new class; the queue, commands and engine
  stay the same.

## Commands

| Text | Effect |
|---|---|
| any description | first message: new app. Later: a change to the active app. "Build me a…app", "new app…" start a new one |
| `NEW <idea>` / `NEW` | start a new app (bare `NEW` asks what it should do) |
| `CHANGE <request>` | change the active app |
| `STATUS [G-XXXXX]` | real stage + progress of the active/last build |
| `PROJECTS` | list your apps (`*` = active) |
| `USE <n>` | switch the active app |
| `OPEN [n]` | fresh download link for the latest successful build |
| `ABORT` / `CANCEL BUILD` (bare `CANCEL` on WhatsApp and web chat) | stop the queued or running build |
| `RETRY` | retry the last failed or cancelled build |
| `HELP` | command list |
| `LINK <code>` | link a new phone (see Identity) |
| `STOP` / `START` | opt out / back in (Twilio's own keywords; bare `CANCEL` is also a Twilio opt-out word, so builds are stopped with `ABORT`) |

If a message could be a change but no app is active, Genesis asks instead of guessing. It never sends source
code by SMS, only status, short summaries and links. Messages are plain ASCII, at most 450 characters (3 segments).

## Identity and security

- Phone numbers are normalized to E.164 and are the identity. Every project, build, status and link lookup is
  scoped to the sender's user ID. Texting someone else's build ID or project number reveals nothing.
- `GENESIS_SMS_OWNER_NUMBERS`: your numbers, trusted immediately.
- Other numbers (with `GENESIS_SMS_SIGNUP=link`) must text `LINK <code>`. Codes are created **only on the
  Genesis computer** (`python -m genesis sms-link-code`, or `POST /api/sms/link-codes` from the local
  dashboard). They are single-use, expire after 15 minutes and are stored hashed. Five wrong codes lock that
  number for an hour. An email address or project ID never grants access.
- `open`: anyone can text and gets an isolated guest account with its own projects and a smaller daily
  quota (`GENESIS_SMS_GUEST_DAILY_BUILDS`). `closed`: owners only.
- Unknown numbers get at most one reply per 24 hours. Each sender is limited to `GENESIS_SMS_INBOUND_PER_HOUR`
  messages, with daily build quotas per user.
- Webhooks: `X-Twilio-Signature` is validated with the official SDK against `PUBLIC_BASE_URL` + path, and
  `AccountSid` must match. Duplicate deliveries (same `MessageSid`) are ignored, and a signature over a
  modified body fails.
- Only `/api/webhooks/twilio/*` and `/download/<token>` are reachable through the tunnel. Requests that
  arrive with proxy headers (`X-Forwarded-For`, `CF-Connecting-IP`, ...) **never** get the local-dashboard
  bypass, so the dashboard API stays private even behind a tunnel.
- Download links: 32 random bytes, stored as SHA-256, bound to one user and one build, expire after
  `GENESIS_SMS_LINK_TTL_HOURS`, at most 25 downloads. They serve only the verified APK (no paths, no bucket
  URLs). `OPEN` issues a fresh link after expiry. A success SMS is sent only after the APK file is confirmed
  on disk.
- Logs: structured `event=sms.* ...` lines with masked numbers (`+91******3210`). Message bodies, tokens,
  auth tokens and source code are never logged. Credentials live only in `.env` (git-ignored) and are
  excluded from the Gradle environment.
- Generated code: Genesis compiles but **never runs** generated apps. Gradle runs in a per-build workspace
  with a scrubbed environment, a server-controlled build script (no model-added dependencies or plugins), a
  timeout, and process-group kill on timeout or cancel. It is not a container: for an internet-facing
  multi-user deployment, run the worker (`GENESIS_SMS_WORKER=external`) as a separate low-privilege OS user
  or VM.

## Configuration

`.env` (see `.env.example`):

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...                 # server-side only
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX      # or TWILIO_MESSAGING_SERVICE_SID=MG...
TWILIO_CHANNEL=sms                    # or whatsapp
PUBLIC_BASE_URL=https://<your-tunnel-or-domain>
GENESIS_SMS_OWNER_NUMBERS=+91XXXXXXXXXX
GENESIS_SMS_SIGNUP=link
```

Check everything (read-only, sends nothing):

```bash
.venv/bin/python -m genesis sms-check
```

## Twilio Console setup

1. **Upgrade from Trial** (Console → Billing). On a trial account, messages only reach Verified Caller IDs and
   start with "Sent from your Twilio trial account".
2. **Get a sender**
   - SMS: Phone Numbers → Buy a number with **SMS** capability. US numbers that text US recipients need
     A2P 10DLC registration (Messaging → Regulatory Compliance); toll-free numbers need toll-free verification.
   - WhatsApp (recommended for India): Messaging → Try it out → **Send a WhatsApp message** (sandbox, for
     testing; each phone first sends `join <code>` to the sandbox number), then register a WhatsApp sender for
     production. Set `TWILIO_WHATSAPP_NUMBER` (the sandbox is `+14155238886`). Trial accounts can send at most
     50 messages a day, and sandbox messages are billed at standard rates from the account balance.
3. **Messaging Geo Permissions** (Messaging → Settings → Geo permissions): enable each destination country
   (e.g. India), or sends fail with error 21408.
4. **Expose Genesis over HTTPS.** Keep `GENESIS_HOST=127.0.0.1` and run a tunnel, for example
   `cloudflared tunnel --url http://127.0.0.1:8765` (or a named tunnel / ngrok / Caddy). Put the https URL in
   `PUBLIC_BASE_URL`. Do not configure the tunnel to rewrite the `Host` header **and** strip forwarding headers.
5. **Webhook.** Phone Numbers → Manage → Active numbers → your number → Messaging configuration →
   "A message comes in": **Webhook**, `https://<PUBLIC_BASE_URL>/api/webhooks/twilio/sms`, **HTTP POST**.
   With a Messaging Service, set the same URL under the service's Integration → "Send a webhook", and make sure
   the number belongs to that service. For the WhatsApp sandbox, use the sandbox settings' "When a message
   comes in" field.
6. **Delivery status** is automatic. Each send sets `StatusCallback` to
   `https://<PUBLIC_BASE_URL>/api/webhooks/twilio/status` (signature-checked), which records
   delivered/undelivered/failed and the Twilio error code in `data/sms.sqlite3`. You can also see each message
   in Console → Monitor → Logs → Messaging, along with error codes such as 30007 (carrier filtered), 30008
   (unknown) and 21610 (STOP).
7. **Signature validation** uses `TWILIO_AUTH_TOKEN`. If you rotate the token, update `.env` and restart.

## Web chat security

`/chat` is public (the page holds nothing). Signing in needs a one-time link code; then the browser gets an
HttpOnly, SameSite=Strict, Secure (over HTTPS) session cookie valid for 30 days. Every chat API call also needs
the `X-Genesis-Chat: 1` header (CSRF). Wrong codes are rate-limited globally. The computer's own browser can sign
in without a code (loopback, local Host, no proxy headers). Each chat user is a separate Genesis user with their
own projects. Messages carry a client id, so a resend after a network error can't start a second build. Web chat
identities can't be used through the Twilio webhook.

## Running

```bash
.venv/bin/python -m genesis serve            # dashboard + webhooks + embedded SMS worker
cloudflared tunnel --url http://127.0.0.1:8765
```

Separate worker (optional): set `GENESIS_SMS_WORKER=external`, then run `.venv/bin/python -m genesis sms-worker`
in its own process (systemd/launchd). Jobs are leased, so if a worker is killed, its job resumes on the next
worker. Several workers are safe, but each one runs its own Gradle builds, so on one machine use one.

Inspect state on the Genesis computer: `curl http://127.0.0.1:8765/api/sms/status` (counts, events, config
problems; no secrets), and `sqlite3 data/sms.sqlite3 'select ref,status,attempts,error from jobs order by id desc limit 10'`.

## Testing

```bash
.venv/bin/python -m pytest -q                                   # offline; Twilio and Gemini are faked
GENESIS_RUN_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_sms_integration.py   # real Gradle build
GENESIS_RUN_INTEGRATION=1 GENESIS_RUN_GEMINI=1 ...              # + real Gemini (uses API quota)
```

Local end-to-end without sending a text (real Gemini + Gradle; replies are printed and written to
`data/sms-outbox.log`):

```bash
.venv/bin/python -m genesis sms-simulate --from +91XXXXXXXXXX "Build me a habit tracker with streaks"
.venv/bin/python -m genesis sms-simulate --from +91XXXXXXXXXX "Make the theme dark"
```

(The number must be in `GENESIS_SMS_OWNER_NUMBERS` or linked first.)

From your phone, once the Console steps are done: text `HELP`, then an app idea. You should get the
acknowledgement within seconds, progress texts as stages change, and a link that downloads the APK on the phone.
Then text a change.

## India: what works and what doesn't

Checked October 2026 against Twilio's India guidelines and help center:

- **SMS to Indian mobiles is one-way.** Indian carriers replace the sender with a random 5–9 digit short code,
  so recipients **cannot reply** to a Twilio number. Indian operators don't support international or domestic
  long codes as senders.
- **DLT.** Domestic traffic (an Indian entity sending to India) requires company and Sender ID registration on
  an operator DLT portal before Twilio registration (about 10 business days), and even then only
  alphanumeric, one-way sender IDs. International traffic doesn't need DLT but still overwrites the sender.
- Whether an Indian phone can **send** an SMS to a US Twilio number depends on the user's carrier and plan
  (international SMS is often blocked on prepaid plans). Even when it works, Genesis's replies arrive from a
  random short code, so it isn't a usable conversation.
- **Recommended:** Twilio API for WhatsApp (`TWILIO_CHANNEL=whatsapp`). It is two-way with Indian numbers,
  uses the same webhook, signature validation and code path, and needs no DLT. Free-form replies are allowed
  within 24 hours of the user's last message, which covers build times.
- Alternative: an Indian SMS gateway with DLT-registered templates plus a two-way virtual number, added as a
  new `SmsProvider`.

## Talking to Genesis (plain English and voice notes)

**Chat brain (default on, `GENESIS_CHAT_BRAIN=on`).** Every message that isn't an exact command goes to the
AI backend (Antigravity, or the Gemini API) with the last 12 messages, the user's apps and any running build.
It answers like a person (questions, brainstorming, one clarifying question when an idea is vague) and picks
one action: reply only, build a new app (with a full spec from the conversation), change an app, status,
list, download link, switch, cancel or retry. Genesis carries the action out with its normal checks (one
build at a time, quotas, the user's own apps only), so the model can't do more than the user's own commands.
With Antigravity each message is a short "Genesis chat" conversation there (usually a few seconds). If the
backend fails or takes longer than `GENESIS_CHAT_TIMEOUT_SECONDS` (90), the built-in rules below answer.

You don't need commands. Genesis understands everyday messages, for example "make the buttons bigger"
(change the active app), "I want an app that tracks my water" (new app), "how's it going?", "send me the
link", "show my apps", "switch to the lift log one", "cancel it" and "try again". Small talk ("hi",
"thanks") never starts a build. When a message could be either a new app or a change, Genesis asks
"change or new?" instead of guessing. The old commands (STATUS, USE 2, OPEN, ...) still work.

**Voice notes** (WhatsApp, or MMS audio) are transcribed on this computer with Whisper (`faster-whisper`),
with no API and no cost. Genesis replies starting with `You said: "..."` so you can check what it heard. Only linked
users' notes are transcribed, media is only downloaded from `api.twilio.com` for this account, and the
audio is deleted right after transcription. Settings: `GENESIS_VOICE=on|off`, `GENESIS_VOICE_MODEL`
(`tiny`/`base` (default)/`small`/`medium`; bigger is more accurate and slower), `GENESIS_VOICE_LANGUAGE`
(empty = auto-detect, or e.g. `en`, `hi`). The model downloads once on first use (~145 MB for `base`).

#!/usr/bin/env bash
# Start Genesis reachable from phones over HTTPS: a Cloudflare tunnel + `genesis serve` with PUBLIC_BASE_URL set.
#
#   scripts/genesis_public.sh            # quick tunnel: free, no account, new random URL each run
#   PUBLIC_BASE_URL=https://genesis.example.com scripts/genesis_public.sh   # you already run a named tunnel/proxy
#
# Only /chat, /api/chat/*, /api/webhooks/twilio/*, /download/<token> and /preview/<token>/ work through the tunnel; the dashboard
# stays private to this computer (requests carrying proxy headers never get the local bypass).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${GENESIS_PORT:-8765}"
mkdir -p data

if [ -z "${PUBLIC_BASE_URL:-}" ]; then
  command -v cloudflared >/dev/null || { echo "Install cloudflared first: brew install cloudflared"; exit 1; }
  LOG=data/cloudflared.log
  : > "$LOG"
  cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" >"$LOG" 2>&1 &
  CF_PID=$!
  trap 'kill "$CF_PID" 2>/dev/null || true' EXIT INT TERM
  URL=""
  for _ in $(seq 1 60); do
    URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
    [ -n "$URL" ] && break
    kill -0 "$CF_PID" 2>/dev/null || { echo "cloudflared exited; see $LOG"; exit 1; }
    sleep 1
  done
  [ -n "$URL" ] || { echo "No tunnel URL after 60s; see $LOG"; exit 1; }
  export PUBLIC_BASE_URL="$URL"
fi
echo "$PUBLIC_BASE_URL" > data/public_url

cat <<MSG

  Genesis is reachable at:  $PUBLIC_BASE_URL
  Phone chat:               $PUBLIC_BASE_URL/chat      (get a code: .venv/bin/python -m genesis sms-link-code --hours 24)
  Twilio webhook (POST):    $PUBLIC_BASE_URL/api/webhooks/twilio/sms
  Dashboard (this computer only): http://127.0.0.1:$PORT

MSG
exec .venv/bin/python -m genesis serve

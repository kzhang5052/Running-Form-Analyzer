#!/bin/bash
# Double-click to serve the app to your other devices (iPhone, iPad, laptop).
# Binds to your Tailscale IP if available (reachable anywhere on your tailnet),
# otherwise your local Wi-Fi IP. Open the printed URL on the device, then
# Share → Add to Home Screen to install it as an app.
cd "$(dirname "$0")"

TS="$(tailscale ip -4 2>/dev/null || /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null | head -1)"
if [[ -n "$TS" ]]; then
  HOST="$TS"; NET="Tailscale (works anywhere your devices are signed in)"
else
  HOST="$(ipconfig getifaddr en0 2>/dev/null || echo 0.0.0.0)"; NET="Wi-Fi (same network only)"
fi

echo ""
echo "  Running Form Analyzer — serving over $NET"
echo "  ┌───────────────────────────────────────────────"
echo "  │  On your iPhone/iPad, open:  http://$HOST:5177"
echo "  │  Then: Share ⇧ → Add to Home Screen"
echo "  └───────────────────────────────────────────────"
echo "  Ctrl-C to stop."
echo ""

HOST="$HOST" PORT=5177 .venv/bin/python app.py

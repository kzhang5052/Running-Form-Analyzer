#!/bin/bash
# Build a double-clickable "Running Form Analyzer.app" that launches the local
# server and opens the UI. Uses macOS-native osacompile — no extra tooling.
# Re-run this after moving the project or changing the path.
set -euo pipefail

PROJ="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Running Form Analyzer"
BUILD="$PROJ/$APP_NAME.app"

if [[ ! -x "$PROJ/.venv/bin/python" ]]; then
  echo "⚠️  No .venv found. Set it up first:"
  echo "    cd \"$PROJ\" && uv venv --python 3.12 .venv && uv pip install -r requirements.txt"
  exit 1
fi

# AppleScript source, with the project path baked in.
SRC="$(mktemp -t rfa_app).applescript"
cat > "$SRC" <<APPLESCRIPT
set projDir to "$PROJ"
set venvPy to projDir & "/.venv/bin/python"
set appPy to projDir & "/app.py"
set theURL to "http://127.0.0.1:5177"

-- Boot the server only if it isn't already answering.
set code to (do shell script "curl -s -o /dev/null -w '%{http_code}' " & theURL & "/api/health || true")
if code is not "200" then
	do shell script "cd " & quoted form of projDir & " && nohup " & quoted form of venvPy & " " & quoted form of appPy & " >/tmp/running-form-analyzer.log 2>&1 &"
	repeat 60 times
		delay 0.5
		set code to (do shell script "curl -s -o /dev/null -w '%{http_code}' " & theURL & "/api/health || true")
		if code is "200" then exit repeat
	end repeat
end if

if code is not "200" then
	display dialog "Running Form Analyzer couldn't start. See /tmp/running-form-analyzer.log" buttons {"OK"} default button "OK" with icon stop
	return
end if

-- Prefer a chrome-less app window (Chrome/Edge/Brave); fall back to the browser.
set opened to false
repeat with b in {"Google Chrome", "Microsoft Edge", "Brave Browser"}
	try
		do shell script "open -a " & quoted form of (b as text) & " --args --app=" & theURL
		set opened to true
		exit repeat
	end try
end repeat
if not opened then do shell script "open " & theURL
APPLESCRIPT

rm -rf "$BUILD"
osacompile -o "$BUILD" "$SRC"
rm -f "$SRC"

# Make it findable in Spotlight/Launchpad (no sudo needed).
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/$APP_NAME.app"
cp -R "$BUILD" "$HOME/Applications/$APP_NAME.app"

echo "✅ Built: $BUILD"
echo "   Also installed to: $HOME/Applications/$APP_NAME.app (Spotlight: '$APP_NAME')"
echo "   Double-click it to launch. To stop the server: lsof -ti:5177 | xargs kill"

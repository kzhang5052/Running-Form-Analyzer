#!/bin/bash
# One-time setup: generate the Xcode project + install the MediaPipe pod.
# Requires full Xcode (not just Command Line Tools) and Homebrew.
set -euo pipefail
cd "$(dirname "$0")"

if ! xcode-select -p 2>/dev/null | grep -q "Xcode.app"; then
  echo "⚠️  Full Xcode is required (you currently have only Command Line Tools)."
  echo "    1. Install Xcode from the App Store."
  echo "    2. sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
  echo "    3. Re-run this script."
  exit 1
fi

command -v xcodegen >/dev/null 2>&1 || { echo "Installing xcodegen…"; brew install xcodegen; }
command -v pod       >/dev/null 2>&1 || { echo "Installing cocoapods…"; brew install cocoapods; }

echo "Generating Xcode project…"; xcodegen generate
echo "Installing pods…";          pod install

echo ""
echo "✅ Done. Now:"
echo "   open RunningForm.xcworkspace"
echo "   • In Signing & Capabilities, pick your Apple ID team (free is fine)."
echo "   • Plug in your iPhone, select it, and press Run (⌘R)."
echo "   Free-account builds re-sign every 7 days — just re-Run from Xcode."

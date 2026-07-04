#!/bin/bash
# Compile + run the pure metric math with the Command Line Tools swift.
# No Xcode or MediaPipe needed — verifies the port in analyzer.py -> Swift.
set -euo pipefail
cd "$(dirname "$0")"
OUT="$(mktemp -d)/formcheck"
swiftc -O RunningForm/FormAnalyzer.swift Tests/SelfCheckMain.swift -o "$OUT"
"$OUT"

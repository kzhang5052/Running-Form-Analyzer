# Form/Check — native iOS app (offline, on-device)

A SwiftUI app that analyzes your running form **entirely on the iPhone** — no
server, no network. It runs MediaPipe's Pose Landmarker on-device and computes
the same metrics as the Python app (cadence, foot strike, trunk lean, pelvic
drop, crossover, vertical oscillation, symmetry, arm carry), each with the
study it's grounded in.

## Prerequisites

- **Full Xcode** (App Store) — you currently have only Command Line Tools. After
  installing: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
- **Homebrew** (you have it) — used to install XcodeGen + CocoaPods.
- A **free Apple ID** is enough to run on your own iPhone. The $99/yr Apple
  Developer Program is only needed for TestFlight / the App Store. Free-account
  builds must be re-run from Xcode every 7 days (the signing expires).

## Build & run

```bash
cd ios
./setup.sh                 # installs xcodegen + cocoapods, generates the project, pod install
open RunningForm.xcworkspace
```

In Xcode: select the **RunningForm** target → **Signing & Capabilities** → pick
your Apple ID **Team** (Xcode auto-creates a free personal team). Plug in your
iPhone, choose it as the run destination, press **⌘R**. First launch on the
phone: Settings → General → VPN & Device Management → trust your developer cert.

## What v1 does

Pick a running clip from your library → it extracts frames (upright, first 30 s),
runs pose per frame on-device, and shows the stride report: headline stats, a
worst-first list of cited coaching cards, and a References section. Auto-detects
side vs front/rear view and adapts the metrics.

## Verify the math without Xcode

The metric engine (`RunningForm/FormAnalyzer.swift`) is pure Foundation and has
a self-check that compiles with the Command Line Tools compiler:

```bash
./selfcheck.sh     # -> selfcheck OK · view=frontal · pelvic_drop=7.7° · cadence=180 · cards=6
```

## Deferred (easy follow-ups)

- **In-app recording** — v1 picks an existing clip; recording is a small
  `UIImagePickerController` add (or `AVCaptureSession`).
- **Annotated video export** — the skeleton overlay + strike markers the web app
  renders. Needs an `AVAssetWriter` pass; the report shows the numbers for now.
- **Charts** — the ankle-trace / pelvis-tilt plots.

## Notes

- The pose model (`Resources/pose_landmarker_full.task`, 9 MB) is the exact file
  the Python app uses — bundled into the app, so everything is offline.
- The generated `.xcodeproj` / `.xcworkspace` / `Pods/` are gitignored; they're
  reproduced by `setup.sh`.

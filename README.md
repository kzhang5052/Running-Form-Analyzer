# 🏃 Running Form Analyzer

Analyze your running form from a video, fully locally on your Mac. Upload a
clip, get back an annotated video (skeleton + foot strikes) plus metrics and
coaching feedback. **The camera angle is detected automatically** and the
metrics adapt to it:

**Side view (sagittal):**
- **Cadence** (steps/min)
- **Overstriding** — shin angle & foot reach at contact
- **Foot-strike type** — heel / midfoot / forefoot, by the Altman–Davis
  foot-strike angle (>8° rearfoot, −1.6–8° midfoot, <−1.6° forefoot)
- **Trunk lean**
- **Knee angle at landing** (stiff-leg landing check)

**Front / rear view (frontal):**
- **Contralateral pelvic drop** — the strongest gait predictor of running
  injury in the literature
- **Crossover / stride width** — feet landing on the midline

**Either view:** vertical oscillation (bounce; in cm if you give your height),
left/right symmetry, arm carry.

Every coaching note is grounded in a named study and links to it (Bramah 2018,
Heiderscheit 2011, Folland 2017, Altman & Davis 2012, Teng & Powers 2014); the
report ends with a References section. Built on MediaPipe pose estimation (33
landmarks/frame). Nothing is uploaded anywhere — it all runs on-device.

## Run the web app

```bash
cd ~/Claude/Projects/running-form-analyzer
.venv/bin/python app.py
# then open http://127.0.0.1:5177
```

## Use it as an API

The server exposes a JSON HTTP API (CORS-open, runs alongside the web UI). One
call, blocking:

```bash
curl -X POST http://127.0.0.1:5177/api/analyze/sync -F "video=@run.mp4" -F "height=183"
```

Returns the full report (metrics, cited feedback, references, chart) plus a
`video_url` for the annotated clip. There's also an async job flow for long
clips and a `/api/health` check. See [API.md](API.md) for all endpoints.

## Or use the CLI

```bash
.venv/bin/python analyzer.py path/to/run.mp4 --height 183
# writes run_annotated.mp4 + run_annotated.json next to your video
```

## Filming tips (matter a lot)

- **Side view**, camera roughly hip height, phone steady (prop it up or have
  someone hold it still).
- Whole body in frame for the entire clip; 5–15 s of continuous running.
- Treadmill side-view is ideal. Outdoors, run past a stationary camera.
- Good light; avoid heavy backlight. Only the first 30 s are analyzed.

## How the numbers are computed

Foot strikes are detected as the lowest points of each ankle's trajectory.
At each strike the shin angle, knee angle, foot reach (ankle ahead of hip,
in leg-lengths), and heel-vs-toe height (strike type) are measured. Cadence
comes from the merged strike train; bounce from the detrended hip midpoint;
trunk lean from the shoulder–hip line vs vertical. The cm bounce estimate
assumes hip-to-ankle leg length ≈ 0.49 × your height.

Single-camera pose estimation is directional, not lab-grade — compare videos
filmed the same way, change one thing at a time, and see a professional if
something hurts.

## Project layout

- `analyzer.py` — pose extraction, gait metrics, feedback rules, video rendering (also a CLI)
- `app.py` — Flask backend: serves the UI, upload → background job → JSON report API
- `ui/` — React + TypeScript + Tailwind + shadcn/ui frontend ("Form/Check")
  - served as a single pre-bundled file, `ui/bundle.html` — no Node needed to run the app
  - to change the UI: edit `ui/src/`, then rebuild the bundle with the
    web-artifacts-builder skill's `bundle-artifact.sh` (requires Node + pnpm)
- `models/pose_landmarker_full.task` — MediaPipe pose model (downloaded once)
- `uploads/`, `outputs/` — transient videos and reports (safe to empty)

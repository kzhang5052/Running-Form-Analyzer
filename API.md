# Running Form Analyzer — HTTP API

Start the server (also serves the web UI):

```bash
.venv/bin/python app.py            # http://127.0.0.1:5177
HOST=0.0.0.0 PORT=8080 .venv/bin/python app.py   # expose it / change port
```

All responses are JSON (except `/video/<id>`, which streams MP4). CORS is open
(`Access-Control-Allow-Origin: *`) so other tools and web pages can call it.
Upload limit: 500 MB. Accepted: mp4, mov, m4v, avi, webm, mkv.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/analyze/sync` | Analyze a video and return the full report in one call (blocking). |
| `POST` | `/api/analyze` | Same input, returns a `job_id` immediately; poll for the result. (alias: `/upload`) |
| `GET`  | `/api/job/<id>` | Job status + progress. |
| `GET`  | `/api/result/<id>` | Full report JSON for a finished job. |
| `GET`  | `/video/<id>` | Annotated MP4 for a job. |
| `GET`  | `/api/health` | `{status, api_version, model}`. |

Request body for the two analyze endpoints is `multipart/form-data`:
`video` (file, required), `height` (cm, optional — enables the bounce estimate
in cm).

## One-call (synchronous)

Best for scripts and short clips. Holds the connection open while it processes
(~a few seconds per 10 s of video).

```bash
curl -X POST http://127.0.0.1:5177/api/analyze/sync \
  -F "video=@run.mp4" -F "height=183"
```

```jsonc
{
  "job_id": "c273ce5f6ce5",
  "video_url": "/video/c273ce5f6ce5",
  "metrics": {
    "view": "sagittal",              // or "frontal" — auto-detected
    "cadence": 178.2,
    "foot_strike_type": "midfoot",
    "foot_strike_angle_deg": 4.1,    // Altman–Davis
    "trunk_lean_deg": 6.3,
    "shin_angle_deg": 3.0,
    "knee_angle_at_strike": 158.0,
    "pelvic_drop_deg": 4.2,          // meaningful in frontal view
    "stride_width_ratio": 1.3,       // meaningful in frontal view
    "vo_cm": 8.4, "vo_pct_leg": 9.1,
    "symmetry_pct": 3.0,
    "n_steps": 16, "duration_s": 6.0,
    "warnings": []
  },
  "feedback": [
    { "status": "warn|info|good", "title": "Cadence", "value": "178 spm",
      "message": "…", "source": { "cite": "…", "note": "…", "url": "…" } }
  ],
  "references": [ { "cite": "…", "note": "…", "url": "…" } ],
  "chart": { "t": [...], "l_ankle_y": [...], "r_ankle_y": [...],
             "lean": [...], "pelvis_obliq": [...], "strikes": [...] }
}
```

Errors: `400` bad/missing file, `422` a valid video that couldn't be analyzed
(too short, no runner visible — message explains), `413` over 500 MB.

## Async (job + poll)

Best for long clips or many concurrent callers — doesn't tie up the connection.

```bash
# 1. submit
curl -X POST http://127.0.0.1:5177/api/analyze -F "video=@run.mp4"
# -> {"job_id":"ab12cd34ef56"}

# 2. poll
curl http://127.0.0.1:5177/api/job/ab12cd34ef56
# -> {"status":"processing","progress":0.42,"error":null}   (status: processing|done|error|unknown)

# 3. fetch report when done
curl http://127.0.0.1:5177/api/result/ab12cd34ef56
```

## Python (no server)

The core is importable — no HTTP needed:

```python
import analyzer
result = analyzer.analyze("run.mp4", "run_annotated.mp4", height_cm=183)
print(result["metrics"]["cadence"], result["metrics"]["view"])
```

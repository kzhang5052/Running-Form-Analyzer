"""Local web app for running-form analysis: upload a video, get a report.

Serves the bundled React UI (ui/bundle.html) and a small JSON API.
"""

import json
import os
import threading
import time
import uuid

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory

import analyzer

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
OUTPUTS = os.path.join(BASE, "outputs")
BUNDLE = os.path.join(BASE, "ui", "bundle.html")
PWA = os.path.join(BASE, "pwa")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

# PWA head tags injected into the bundled SPA so it installs to the home screen
# (iPhone: Share → Add to Home Screen; Mac: browser → Install) and runs
# fullscreen. Read/patched once at startup — rebuilds of the bundle need a
# server restart, which is already the case.
_PWA_HEAD = (
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<meta name="theme-color" content="#0a0c0e">'
    '<meta name="mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
    '<meta name="apple-mobile-web-app-title" content="Form/Check">'
    '<link rel="apple-touch-icon" href="/icons/icon-180.png">'
    "<script>if('serviceWorker' in navigator){addEventListener('load',"
    "function(){navigator.serviceWorker.register('/sw.js')})}</script>"
)


def _index_html():
    html = open(BUNDLE, encoding="utf-8").read()
    # viewport-fit=cover lets the fullscreen app draw under the iPhone notch.
    html = html.replace(
        '<meta name=viewport content="width=device-width, initial-scale=1.0">',
        '<meta name=viewport content="width=device-width, initial-scale=1.0, '
        'viewport-fit=cover">')
    return html.replace("<body", _PWA_HEAD + "<body", 1)


INDEX_HTML = _index_html()

API_VERSION = "1.0"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

ALLOWED = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
jobs = {}  # id -> {status, progress, error}


@app.after_request
def _cors(resp):
    # Local-first tool; allow any origin so scripts/other apps can call the API.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


def _accept_video(req):
    """Validate + save an uploaded video. On success returns
    (job_id, path, height_cm); on failure (None, error_message, status_code)."""
    f = req.files.get("video")
    if not f or not f.filename:
        return None, "No video file received.", 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return None, (f"Unsupported file type '{ext}'. Use MP4, MOV, M4V, "
                      f"AVI, WEBM, or MKV."), 400
    height_cm = None
    try:
        raw = (req.form.get("height") or "").strip()
        if raw:
            height_cm = float(raw)
            if not 100 <= height_cm <= 230:
                height_cm = None
    except ValueError:
        pass
    job_id = uuid.uuid4().hex[:12]
    video_path = os.path.join(UPLOADS, job_id + ext)
    f.save(video_path)
    return job_id, video_path, height_cm


def _run_job(job_id, video_path, height_cm):
    job = jobs[job_id]

    def progress(p):
        job["progress"] = p

    try:
        out_video = os.path.join(OUTPUTS, job_id + ".mp4")
        result = analyzer.analyze(video_path, out_video,
                                  height_cm=height_cm, progress=progress)
        with open(os.path.join(OUTPUTS, job_id + ".json"), "w") as f:
            json.dump(result, f)
        job["status"] = "done"
    except analyzer.AnalysisError as e:
        job["status"] = "error"
        job["error"] = str(e)
    except Exception as e:  # noqa: BLE001 — surface anything to the UI
        job["status"] = "error"
        job["error"] = f"Unexpected error: {e}"
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/manifest.webmanifest")
def manifest():
    return send_file(os.path.join(PWA, "manifest.webmanifest"),
                     mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    return send_file(os.path.join(PWA, "sw.js"), mimetype="text/javascript")


@app.route("/icons/<path:name>")
def icons(name):
    return send_from_directory(os.path.join(PWA, "icons"), name)


# Old-style links from before the SPA — forward to hash routes
@app.route("/job/<job_id>")
def job_page(job_id):
    return redirect(f"/#/job/{job_id}")


@app.route("/result/<job_id>")
def result_page(job_id):
    return redirect(f"/#/result/{job_id}")


@app.route("/upload", methods=["POST"])
@app.route("/api/analyze", methods=["POST"])
def upload():
    """Async: accept a video and return a job_id to poll (used by the web UI)."""
    job_id, video_path, height_cm = _accept_video(request)
    if job_id is None:
        return jsonify({"error": video_path}), height_cm  # (msg, status)
    jobs[job_id] = {"status": "processing", "progress": 0.0, "error": None,
                    "created": time.time()}
    threading.Thread(target=_run_job, args=(job_id, video_path, height_cm),
                     daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/analyze/sync", methods=["POST"])
def analyze_sync():
    """One-call API: block until analysis finishes, return the full report.

    ponytail: holds the request open for the clip's processing time (a few
    seconds per 10s of video) and ties up one worker. Fine for scripting and
    short clips; use POST /api/analyze + poll /api/job/<id> for long clips or
    many concurrent callers.
    """
    job_id, video_path, height_cm = _accept_video(request)
    if job_id is None:
        return jsonify({"error": video_path}), height_cm  # (msg, status)
    try:
        out_video = os.path.join(OUTPUTS, job_id + ".mp4")
        result = analyzer.analyze(video_path, out_video, height_cm=height_cm)
        with open(os.path.join(OUTPUTS, job_id + ".json"), "w") as f:
            json.dump(result, f)
    except analyzer.AnalysisError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:  # noqa: BLE001 — return JSON, not an HTML 500
        return jsonify({"error": f"Unexpected error: {e}"}), 500
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass
    result["job_id"] = job_id
    result["video_url"] = f"/video/{job_id}"
    return jsonify(result)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "api_version": API_VERSION,
                    "model": os.path.basename(analyzer.MODEL_PATH)})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Video exceeds the 500 MB limit."}), 413


@app.route("/api/job/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        if os.path.exists(os.path.join(OUTPUTS, job_id + ".json")):
            return jsonify({"status": "done", "progress": 1.0})
        return jsonify({"status": "unknown"}), 404
    return jsonify({"status": job["status"], "progress": job["progress"],
                    "error": job["error"]})


@app.route("/api/result/<job_id>")
def api_result(job_id):
    path = os.path.join(OUTPUTS, job_id + ".json")
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="application/json")


@app.route("/video/<job_id>")
def video(job_id):
    return send_from_directory(OUTPUTS, job_id + ".mp4")


if __name__ == "__main__":
    # HOST=0.0.0.0 to expose the API beyond localhost (e.g. in a container).
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5177")), debug=False)

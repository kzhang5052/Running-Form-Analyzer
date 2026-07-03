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
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(OUTPUTS, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

ALLOWED = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
jobs = {}  # id -> {status, progress, error}


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
    return send_file(BUNDLE)


# Old-style links from before the SPA — forward to hash routes
@app.route("/job/<job_id>")
def job_page(job_id):
    return redirect(f"/#/job/{job_id}")


@app.route("/result/<job_id>")
def result_page(job_id):
    return redirect(f"/#/result/{job_id}")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("video")
    if not f or not f.filename:
        return jsonify({"error": "No video file received."}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return jsonify({"error": f"Unsupported file type '{ext}'. Use MP4, "
                                 f"MOV, M4V, AVI, WEBM, or MKV."}), 400
    height_cm = None
    try:
        raw = (request.form.get("height") or "").strip()
        if raw:
            height_cm = float(raw)
            if not 100 <= height_cm <= 230:
                height_cm = None
    except ValueError:
        pass

    job_id = uuid.uuid4().hex[:12]
    video_path = os.path.join(UPLOADS, job_id + ext)
    f.save(video_path)
    jobs[job_id] = {"status": "processing", "progress": 0.0, "error": None,
                    "created": time.time()}
    threading.Thread(target=_run_job, args=(job_id, video_path, height_cm),
                     daemon=True).start()
    return jsonify({"job_id": job_id})


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
    app.run(host="127.0.0.1", port=5177, debug=False)

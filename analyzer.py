"""Running form analysis from video using MediaPipe Pose.

Pipeline:
  1. Run pose landmarker over every frame (capped at MAX_SECONDS).
  2. Build smoothed time series of key joints.
  3. Detect foot strikes (local maxima of ankle height-from-top, i.e. lowest points).
  4. Compute gait metrics: cadence, trunk lean, overstride/shin angle, knee angles,
     vertical oscillation, foot-strike type, L/R symmetry, arm carry.
  5. Render an annotated video (skeleton + HUD + strike flashes) and transcode to H.264.
"""

import math
import os
import subprocess

import cv2
import numpy as np
from scipy.signal import find_peaks, savgol_filter

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "pose_landmarker_full.task")

MAX_SECONDS = 30          # analyze at most this much video
MAX_HEIGHT = 720          # downscale frames taller than this
VIS_THRESH = 0.5          # landmark visibility cutoff

# Landmark indices (MediaPipe Pose, 33 points)
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT, R_FOOT = 31, 32

SKELETON = [
    (L_SHOULDER, R_SHOULDER), (L_HIP, R_HIP),
    (L_SHOULDER, L_HIP), (R_SHOULDER, R_HIP),
    (L_SHOULDER, L_ELBOW), (L_ELBOW, L_WRIST),
    (R_SHOULDER, R_ELBOW), (R_ELBOW, R_WRIST),
    (L_HIP, L_KNEE), (L_KNEE, L_ANKLE),
    (R_HIP, R_KNEE), (R_KNEE, R_ANKLE),
    (L_ANKLE, L_HEEL), (L_HEEL, L_FOOT), (L_ANKLE, L_FOOT),
    (R_ANKLE, R_HEEL), (R_HEEL, R_FOOT), (R_ANKLE, R_FOOT),
]


class AnalysisError(Exception):
    pass


# Literature the thresholds and messages are grounded in. Each feedback card
# carries a key into this table so the UI can cite its source.
CITATIONS = {
    "heiderscheit2011": {
        "cite": "Heiderscheit et al. 2011, Med Sci Sports Exerc",
        "note": "+5–10% step rate cut knee energy absorption 20–34% and reduced "
                "vertical COM excursion and step length.",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3022995/",
    },
    "altman2012": {
        "cite": "Altman & Davis 2012, Gait & Posture",
        "note": "Foot-strike angle cutoffs: >8° rearfoot, −1.6°–8° midfoot, "
                "<−1.6° forefoot.",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3278526/",
    },
    "folland2017": {
        "cite": "Folland et al. 2017, Med Sci Sports Exerc",
        "note": "Pelvis vertical oscillation was the kinematic variable most "
                "strongly related to running economy (r=0.53); lower is better.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/28263283/",
    },
    "bramah2018": {
        "cite": "Bramah et al. 2018, Am J Sports Med",
        "note": "Injured runners showed greater contralateral pelvic drop, "
                "greater forward trunk lean, and a more extended knee at contact. "
                "Pelvic drop was the strongest predictor — each 1° raised injury "
                "odds ~80%.",
        "url": "https://journals.sagepub.com/doi/full/10.1177/0363546518793657",
    },
    "teng2014": {
        "cite": "Teng & Powers 2014, JOSPT",
        "note": "Greater forward trunk flexion lowered patellofemoral joint "
                "stress; too upright raises knee load.",
        "url": "https://www.jospt.org/doi/10.2519/jospt.2014.5575",
    },
}


def _interp_nan(a):
    """Linearly interpolate NaNs; returns copy and fraction that was missing."""
    a = a.astype(float).copy()
    n = len(a)
    bad = np.isnan(a)
    if bad.all():
        return a, 1.0
    idx = np.arange(n)
    a[bad] = np.interp(idx[bad], idx[~bad], a[~bad])
    return a, bad.mean()


def _smooth(a, fps, seconds=0.08):
    win = max(5, int(round(fps * seconds)) | 1)  # odd
    if len(a) <= win:
        return a
    return savgol_filter(a, win, 2)


def _angle_at(b, a, c):
    """Angle ABC in degrees at vertex b (points are (x, y))."""
    v1 = np.array(a) - np.array(b)
    v2 = np.array(c) - np.array(b)
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    return math.degrees(math.acos(np.clip(cos, -1, 1)))


def extract_landmarks(video_path, progress=None):
    """First pass: pose landmarks for every frame.

    Returns (lm array [n_frames, 33, 3] of x_px, y_px, visibility with NaN
    where undetected, fps, (width, height), n_frames_total_read).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise AnalysisError("Could not open the video file.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1 or fps > 240 or math.isnan(fps):
        fps = 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    max_frames = int(MAX_SECONDS * fps)

    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)

    frames_lm = []
    size = None
    i = 0
    while i < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if h > MAX_HEIGHT:
            scale = MAX_HEIGHT / h
            frame = cv2.resize(frame, (int(w * scale), MAX_HEIGHT))
            h, w = frame.shape[:2]
        size = (w, h)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts_ms = int(i * 1000.0 / fps)
        result = landmarker.detect_for_video(mp_img, ts_ms)
        if result.pose_landmarks:
            pts = result.pose_landmarks[0]
            arr = np.array([[p.x * w, p.y * h, p.visibility] for p in pts])
        else:
            arr = np.full((33, 3), np.nan)
        frames_lm.append(arr)
        i += 1
        if progress and total:
            progress(0.75 * min(1.0, i / min(total, max_frames)))
    cap.release()
    landmarker.close()

    if not frames_lm:
        raise AnalysisError("The video contains no readable frames.")
    return np.array(frames_lm), fps, size, i


def _series(lm, idx, axis):
    """Time series of one landmark coordinate (NaN where no person detected).

    MediaPipe estimates positions even for occluded joints, so we keep the
    coordinates and use visibility separately as a quality signal.
    """
    return lm[:, idx, axis].copy()


def compute_metrics(lm, fps, size, height_cm=None):
    n = len(lm)
    warnings = []

    detected = ~np.isnan(lm[:, NOSE, 0])
    if detected.mean() < 0.5:
        raise AnalysisError(
            "A person was only detected in {:.0f}% of frames. Make sure the runner "
            "is clearly visible, well lit, and fills a good part of the frame."
            .format(detected.mean() * 100))
    if detected.mean() < 0.85:
        warnings.append("Pose was lost in {:.0f}% of frames; results may be noisy."
                        .format((1 - detected.mean()) * 100))

    # Interpolated + smoothed series (pixel coords) + mean visibility per joint
    S = {}
    vis = {}
    for name, idx in [("nose", NOSE),
                      ("l_sh", L_SHOULDER), ("r_sh", R_SHOULDER),
                      ("l_el", L_ELBOW), ("r_el", R_ELBOW),
                      ("l_wr", L_WRIST), ("r_wr", R_WRIST),
                      ("l_hip", L_HIP), ("r_hip", R_HIP),
                      ("l_knee", L_KNEE), ("r_knee", R_KNEE),
                      ("l_ankle", L_ANKLE), ("r_ankle", R_ANKLE),
                      ("l_heel", L_HEEL), ("r_heel", R_HEEL),
                      ("l_foot", L_FOOT), ("r_foot", R_FOOT)]:
        x, _ = _interp_nan(_series(lm, idx, 0))
        y, _ = _interp_nan(_series(lm, idx, 1))
        S[name] = (_smooth(x, fps), _smooth(y, fps))
        vis[name] = float(np.nanmean(lm[:, idx, 2]))

    leg_vis = np.mean([vis[k] for k in
                       ("l_hip", "r_hip", "l_knee", "r_knee", "l_ankle", "r_ankle")])
    if leg_vis < 0.45:
        warnings.append("Hips/legs were often obscured — film from the side with "
                        "the whole body in frame for more reliable numbers.")

    mid_hip_x = (S["l_hip"][0] + S["r_hip"][0]) / 2
    mid_hip_y = (S["l_hip"][1] + S["r_hip"][1]) / 2
    mid_sh_x = (S["l_sh"][0] + S["r_sh"][0]) / 2
    mid_sh_y = (S["l_sh"][1] + S["r_sh"][1]) / 2

    # Direction of travel (+1 = moving right in frame). Falls back to facing
    # direction (toes vs heels) for treadmill videos.
    disp = np.median(np.gradient(mid_hip_x)) * n
    if abs(disp) > 0.05 * size[0]:
        direction = 1.0 if disp > 0 else -1.0
        treadmill = False
    else:
        toe_heel = np.median(np.concatenate([S["l_foot"][0] - S["l_heel"][0],
                                             S["r_foot"][0] - S["r_heel"][0]]))
        direction = 1.0 if toe_heel >= 0 else -1.0
        treadmill = True

    # Body scale: hip-to-ankle leg length in px (median of summed segments)
    def seg(a, b):
        return np.hypot(S[a][0] - S[b][0], S[a][1] - S[b][1])
    leg_px = np.median((seg("l_hip", "l_knee") + seg("l_knee", "l_ankle") +
                        seg("r_hip", "r_knee") + seg("r_knee", "r_ankle")) / 2)
    px_per_cm = leg_px / (0.49 * height_cm) if height_cm else None

    # --- Camera view: sagittal (side) vs frontal (front/rear) ---
    # Side-on, the shoulders line up front-to-back so their horizontal spread is
    # small next to torso height; face-on it is wide. Threshold calibrated on
    # real clips. Frontal unlocks pelvic drop / crossover; sagittal unlocks
    # shin angle, foot strike, trunk lean.
    shoulder_w = np.median(np.abs(S["l_sh"][0] - S["r_sh"][0]))
    torso_h = np.median(np.abs(mid_sh_y - mid_hip_y)) + 1e-9
    # ponytail: single-ratio classifier, threshold from side≈0.2–0.5 vs
    # front≈0.8–1.2 on real clips. Add limb-visibility symmetry if it misfires.
    view_ratio = shoulder_w / torso_h
    view = "frontal" if view_ratio > 0.62 else "sagittal"

    # --- Pelvic obliquity (frontal plane), signed deg off horizontal ---
    pelvis_obliq = np.degrees(np.arctan2(S["r_hip"][1] - S["l_hip"][1],
                                         np.abs(S["r_hip"][0] - S["l_hip"][0]) + 1e-9))

    # --- Foot strikes: ankle at its lowest point (max y) ---
    min_dist = max(3, int(0.45 * fps))
    strikes = {}
    for side, ankle in [("L", "l_ankle"), ("R", "r_ankle")]:
        y = S[ankle][1]
        rng = np.percentile(y, 95) - np.percentile(y, 5)
        peaks, _ = find_peaks(y, distance=min_dist, prominence=max(2.0, 0.12 * rng))
        strikes[side] = peaks

    all_strikes = sorted([(f, s) for s in strikes for f in strikes[s]])
    if len(all_strikes) < 4:
        raise AnalysisError(
            "Only {} foot strikes were detected — the clip is too short or the legs "
            "aren't clearly visible. Use a 5–15 second side-view clip of continuous "
            "running.".format(len(all_strikes)))
    if len(all_strikes) < 8:
        warnings.append("Only {} steps detected; metrics are rough averages. "
                        "A 10+ second clip gives more reliable numbers."
                        .format(len(all_strikes)))

    # Cadence (steps/min) from merged strike train
    frames_span = all_strikes[-1][0] - all_strikes[0][0]
    cadence = 60.0 * (len(all_strikes) - 1) / (frames_span / fps)

    # L/R symmetry: per-foot stride intervals
    sym_pct = None
    if len(strikes["L"]) >= 2 and len(strikes["R"]) >= 2:
        li = np.median(np.diff(strikes["L"]))
        ri = np.median(np.diff(strikes["R"]))
        sym_pct = abs(li - ri) / ((li + ri) / 2) * 100

    # --- Per-strike measurements ---
    per_strike = []
    for f, side in all_strikes:
        p = "l_" if side == "L" else "r_"
        hip = (S[p + "hip"][0][f], S[p + "hip"][1][f])
        knee = (S[p + "knee"][0][f], S[p + "knee"][1][f])
        ankle = (S[p + "ankle"][0][f], S[p + "ankle"][1][f])
        heel = (S[p + "heel"][0][f], S[p + "heel"][1][f])
        toe = (S[p + "foot"][0][f], S[p + "foot"][1][f])

        knee_angle = _angle_at(knee, hip, ankle)
        # Shin angle from vertical; positive = ankle ahead of knee (overstride)
        shin = math.degrees(math.atan2(direction * (ankle[0] - knee[0]),
                                       ankle[1] - knee[1] + 1e-9))
        # Foot position relative to hip, in leg lengths, + = ahead of body
        reach = direction * (ankle[0] - hip[0]) / leg_px
        # Foot-strike angle (Altman & Davis 2012): sole inclination off ground.
        # +ve = toe up / dorsiflexed (rearfoot), -ve = toe down (forefoot).
        foot_len = math.hypot(toe[0] - heel[0], toe[1] - heel[1]) + 1e-9
        fsa = math.degrees(math.asin(np.clip((heel[1] - toe[1]) / foot_len, -1, 1)))
        if fsa > 8.0:
            fs_type = "heel"
        elif fsa < -1.6:
            fs_type = "forefoot"
        else:
            fs_type = "midfoot"
        per_strike.append({"frame": int(f), "side": side, "t": f / fps,
                           "knee_angle": knee_angle, "shin_angle": shin,
                           "reach": reach, "fsa": fsa, "type": fs_type})

    shin_med = float(np.median([s["shin_angle"] for s in per_strike]))
    reach_med = float(np.median([s["reach"] for s in per_strike]))
    knee_at_strike = float(np.median([s["knee_angle"] for s in per_strike]))
    fsa_med = float(np.median([s["fsa"] for s in per_strike]))
    fs_counts = {}
    for s in per_strike:
        fs_counts[s["type"]] = fs_counts.get(s["type"], 0) + 1
    fs_dominant = max(fs_counts, key=fs_counts.get)

    # --- Frontal-plane metrics (meaningful when view == "frontal") ---
    # Contralateral pelvic drop: peak obliquity away from level (Bramah 2018).
    cpd_deg = float(np.percentile(np.abs(pelvis_obliq - np.median(pelvis_obliq)), 95))
    # Stride width at contact / crossover: ankle separation vs hip width.
    hip_w = float(np.median(np.abs(S["l_hip"][0] - S["r_hip"][0]))) + 1e-9
    stance_gap = [abs(S["l_ankle"][0][f] - S["r_ankle"][0][f])
                  for f, _ in all_strikes]
    stride_width_ratio = float(np.median(stance_gap)) / hip_w

    # --- Trunk lean (deg forward of vertical, in direction of travel) ---
    lean_series = np.degrees(np.arctan2(direction * (mid_sh_x - mid_hip_x),
                                        (mid_hip_y - mid_sh_y) + 1e-9))
    trunk_lean = float(np.median(lean_series))
    trunk_sd = float(np.std(lean_series))

    # --- Vertical oscillation of the hips ---
    trend_win = max(5, int(round(fps * 1.2)) | 1)
    if len(mid_hip_y) > trend_win:
        trend = savgol_filter(mid_hip_y, trend_win, 2)
    else:
        trend = np.full_like(mid_hip_y, np.mean(mid_hip_y))
    osc = mid_hip_y - trend
    # Median peak-to-peak per step interval
    ptp = []
    sf = [f for f, _ in all_strikes]
    for a, b in zip(sf[:-1], sf[1:]):
        if b - a > 2:
            ptp.append(np.ptp(osc[a:b + 1]))
    vo_px = float(np.median(ptp)) if ptp else float(np.ptp(osc))
    vo_pct_leg = vo_px / leg_px * 100
    vo_cm = vo_px / px_per_cm if px_per_cm else None

    # --- Max knee flexion during swing (min angle) ---
    knee_flex = {}
    for side, p in [("L", "l_"), ("R", "r_")]:
        angles = []
        for f in range(n):
            angles.append(_angle_at(
                (S[p + "knee"][0][f], S[p + "knee"][1][f]),
                (S[p + "hip"][0][f], S[p + "hip"][1][f]),
                (S[p + "ankle"][0][f], S[p + "ankle"][1][f])))
        knee_flex[side] = float(np.percentile(angles, 5))

    # --- Arm carry: median elbow angle ---
    elbow_angles = []
    for p in ["l_", "r_"]:
        if vis[p + "wr"] > 0.5:
            for f in range(0, n, 2):
                elbow_angles.append(_angle_at(
                    (S[p + "el"][0][f], S[p + "el"][1][f]),
                    (S[p + "sh"][0][f], S[p + "sh"][1][f]),
                    (S[p + "wr"][0][f], S[p + "wr"][1][f])))
    elbow_med = float(np.median(elbow_angles)) if elbow_angles else None

    metrics = {
        "n_frames": n, "fps": fps, "duration_s": n / fps,
        "treadmill": treadmill, "direction": direction,
        "view": view, "view_ratio": float(view_ratio),
        "n_steps": len(all_strikes),
        "cadence": cadence,
        "symmetry_pct": sym_pct,
        "trunk_lean_deg": trunk_lean, "trunk_lean_sd": trunk_sd,
        "shin_angle_deg": shin_med,
        "foot_reach_legs": reach_med,
        "knee_angle_at_strike": knee_at_strike,
        "foot_strike_type": fs_dominant,
        "foot_strike_counts": fs_counts,
        "foot_strike_angle_deg": fsa_med,
        "pelvic_drop_deg": cpd_deg,
        "stride_width_ratio": stride_width_ratio,
        "vo_pct_leg": vo_pct_leg, "vo_cm": vo_cm,
        "max_knee_flexion": knee_flex,
        "elbow_angle": elbow_med,
        "warnings": warnings,
    }
    chart = {
        "t": [round(f / fps, 3) for f in range(0, n, max(1, n // 600))],
        "l_ankle_y": list(np.round(size[1] - S["l_ankle"][1], 1)[::max(1, n // 600)]),
        "r_ankle_y": list(np.round(size[1] - S["r_ankle"][1], 1)[::max(1, n // 600)]),
        "lean": list(np.round(lean_series, 2)[::max(1, n // 600)]),
        "pelvis_obliq": list(np.round(pelvis_obliq - np.median(pelvis_obliq), 2)
                             [::max(1, n // 600)]),
        "strikes": [{"t": round(s["t"], 3), "side": s["side"]} for s in per_strike],
    }
    return metrics, per_strike, chart, S


def build_feedback(m):
    """Coaching cards (status, title, value, message, source). Which cards apply
    depends on the camera view: sagittal (side) vs frontal (front/rear)."""
    fb = []
    frontal = m["view"] == "frontal"

    # --- Cadence: valid from any angle (Heiderscheit 2011) ---
    c = m["cadence"]
    if c < 160:
        fb.append(("warn", "Cadence", f"{c:.0f} spm",
                   "On the low side. Heiderscheit et al. found raising step rate "
                   "just 5–10% cut energy absorbed at the knee by 20–34% and "
                   "shortened the overstriding step. Nudge it up ~5% at a time "
                   "with a metronome — quicker, lighter steps, not faster running.",
                   "heiderscheit2011"))
    elif c <= 190:
        fb.append(("good", "Cadence", f"{c:.0f} spm",
                   "In the range where most runners land their foot near the body. "
                   "No change needed — note cadence naturally rises with pace.",
                   "heiderscheit2011"))
    else:
        fb.append(("info", "Cadence", f"{c:.0f} spm",
                   "Quite high — fine for a fast interval or a smaller runner, but "
                   "at easy pace it can mean short, choppy strides.",
                   "heiderscheit2011"))

    # --- Vertical oscillation: valid from any angle (Folland 2017) ---
    if m["vo_cm"] is not None:
        vo_str = f"{m['vo_cm']:.1f} cm (est.)"
        high, mid = m["vo_cm"] > 10.5, m["vo_cm"] > 8.5
    else:
        vo_str = f"{m['vo_pct_leg']:.1f}% of leg length"
        high, mid = m["vo_pct_leg"] > 13, m["vo_pct_leg"] > 10
    if high:
        fb.append(("warn", "Vertical oscillation", vo_str,
                   "Noticeable bounce. Folland et al. found vertical oscillation "
                   "was the movement variable most strongly tied to running "
                   "economy — energy going up and down isn't going forward. Higher "
                   "cadence and a level, smooth gaze usually reduce it.",
                   "folland2017"))
    elif mid:
        fb.append(("info", "Vertical oscillation", vo_str,
                   "A bit of bounce, within the normal range. Worth attention only "
                   "if you're chasing economy.", "folland2017"))
    else:
        fb.append(("good", "Vertical oscillation", vo_str,
                   "Low bounce — energy is going into forward motion, which tracks "
                   "with better running economy.", "folland2017"))

    if frontal:
        # --- Contralateral pelvic drop (Bramah 2018) ---
        cpd = m["pelvic_drop_deg"]
        if cpd > 10:
            fb.append(("warn", "Pelvic drop", f"{cpd:.1f}° peak",
                       "Your hip drops noticeably on the swing side each step. "
                       "Bramah et al. found this the single strongest gait "
                       "predictor of running injury — each extra 1° raised injury "
                       "odds ~80%, across ITB, PFP, shin splints and Achilles "
                       "cases. Usually a glute-med/hip-stability issue; side "
                       "planks and single-leg work help.", "bramah2018"))
        elif cpd > 5:
            fb.append(("info", "Pelvic drop", f"{cpd:.1f}° peak",
                       "A mild hip drop on the swing side. Common and not alarming, "
                       "but worth watching — hip-stability work keeps it in check.",
                       "bramah2018"))
        else:
            fb.append(("good", "Pelvic drop", f"{cpd:.1f}° peak",
                       "Your pelvis stays level through stance — strong sign of "
                       "good hip stability and lower injury risk.", "bramah2018"))

        # --- Stride width / crossover (frontal-plane mechanics, Bramah 2018) ---
        sw = m["stride_width_ratio"]
        if sw < 1.0:
            fb.append(("warn", "Crossover / stride width", f"gap {sw:.1f}× hip width",
                       "Your feet land close to (or across) the midline — a narrow, "
                       "crossover gait. It goes hand in hand with the hip adduction "
                       "and pelvic drop pattern linked to ITB and knee pain. Aim to "
                       "land on 'two rails', not a tightrope.", "bramah2018"))
        else:
            fb.append(("good", "Crossover / stride width", f"gap {sw:.1f}× hip width",
                       "Your feet land in two parallel lines — no crossover. Good "
                       "for frontal-plane knee and hip loading.", "bramah2018"))
    else:
        # --- Sagittal-only cards ---
        shin, reach = m["shin_angle_deg"], m["foot_reach_legs"]
        if shin > 8 or reach > 0.28:
            fb.append(("warn", "Overstriding", f"shin {shin:.0f}° at contact",
                       "Your foot lands well ahead of your body with the shin "
                       "angled forward — a classic overstride that brakes each step "
                       "and raises knee/shin impact. The fix is usually cadence: "
                       "quicker steps bring the foot under your hips.",
                       "heiderscheit2011"))
        elif shin > 4:
            fb.append(("info", "Foot landing", f"shin {shin:.0f}° at contact",
                       "Mild reach in front of the body at contact — common, worth "
                       "changing only if you get shin or knee niggles.",
                       "heiderscheit2011"))
        else:
            fb.append(("good", "Foot landing", f"shin {shin:.0f}° at contact",
                       "Your foot lands close to under your center of mass with a "
                       "near-vertical shin — efficient and low-impact.",
                       "heiderscheit2011"))

        fs = m["foot_strike_type"]
        fsa = m["foot_strike_angle_deg"]
        counts = m["foot_strike_counts"]
        dist = ", ".join(f"{v}× {k}"
                         for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        val = f"mostly {fs} · {fsa:+.0f}° ({dist})"
        if fs == "heel" and (shin > 8 or reach > 0.28):
            fb.append(("warn", "Foot strike", val,
                       "By the Altman–Davis foot-strike angle (>8° = rearfoot) "
                       "you're a heel-striker, and combined with the overstride "
                       "above that amplifies braking. Fixing the overstride softens "
                       "it automatically — don't force a forefoot landing.",
                       "altman2012"))
        else:
            label = {"heel": "Heel-striking with the foot landing under you is "
                             "fine — most elite marathoners do it.",
                     "midfoot": "A midfoot landing — nothing to change.",
                     "forefoot": "A forefoot landing — fine if natural; watch for "
                                 "calf/Achilles tightness with volume."}[fs]
            fb.append(("good", "Foot strike", val,
                       f"{label} (classified by Altman–Davis foot-strike angle.)",
                       "altman2012"))

        ka = m["knee_angle_at_strike"]
        if ka > 172:
            fb.append(("warn", "Knee at landing", f"{ka:.0f}° (nearly straight)",
                       "You land on an almost straight leg. Bramah et al. found "
                       "injured runners contacted the ground with a more extended "
                       "knee — a stiff leg passes impact to the joints instead of "
                       "the muscles. A softer knee (often a byproduct of fixing "
                       "overstride) cushions each step.", "bramah2018"))
        else:
            fb.append(("good", "Knee at landing", f"{ka:.0f}°",
                       "Nice soft knee at contact — muscles absorb the impact, the "
                       "pattern seen in uninjured runners.", "bramah2018"))

        lean = m["trunk_lean_deg"]
        if lean < 1:
            fb.append(("warn", "Trunk lean", f"{lean:.1f}°",
                       "You run very upright (or lean back slightly). Teng & Powers "
                       "found more forward trunk flexion lowers patellofemoral "
                       "(kneecap) stress; too upright brakes the stride and loads "
                       "the knee. Lean slightly from the ankles, not the waist.",
                       "teng2014"))
        elif lean <= 12:
            fb.append(("good", "Trunk lean", f"{lean:.1f}° forward",
                       "A comfortable forward lean. Enough trunk flexion to ease "
                       "knee load without overloading the back.", "teng2014"))
        else:
            fb.append(("warn", "Trunk lean", f"{lean:.1f}° forward",
                       "A lot of forward lean — often bending at the waist, which "
                       "loads the low back and hip flexors, and Bramah linked "
                       "excessive forward lean to injury. Run tall: lean from the "
                       "ankles, chest up.", "bramah2018"))

    # --- Symmetry & arm carry: any view ---
    if m["symmetry_pct"] is not None:
        s = m["symmetry_pct"]
        if s > 8:
            fb.append(("warn", "L/R symmetry", f"{s:.0f}% difference",
                       "Left and right step timing differ noticeably. Can be camera "
                       "noise, but if consistent across videos it's worth a physio "
                       "look or single-side strength work.", None))
        else:
            fb.append(("good", "L/R symmetry", f"{s:.0f}% difference",
                       "Left and right step timing are well matched.", None))

    if m["elbow_angle"] is not None:
        e = m["elbow_angle"]
        if e > 115:
            fb.append(("info", "Arm carry", f"elbow {e:.0f}°",
                       "Arms carried fairly straight/low. Bending nearer ~90° keeps "
                       "the swing compact and aids rhythm.", None))
        elif e < 60:
            fb.append(("info", "Arm carry", f"elbow {e:.0f}°",
                       "Arms quite tightly bent/high — keep shoulders relaxed and "
                       "hands loose.", None))
        else:
            fb.append(("good", "Arm carry", f"elbow {e:.0f}°",
                       "Elbow bend is in a relaxed, efficient range.", None))

    order = {"warn": 0, "info": 1, "good": 2}
    fb.sort(key=lambda x: order[x[0]])
    return [{"status": s, "title": t, "value": v, "message": msg,
             "source": CITATIONS.get(src) if src else None}
            for s, t, v, msg, src in fb]


def render_annotated(video_path, out_path, lm, S, metrics, per_strike, fps, size,
                     progress=None):
    """Second pass: draw skeleton + HUD onto each frame, then transcode to H.264."""
    cap = cv2.VideoCapture(video_path)
    n = metrics["n_frames"]
    w, h = size
    tmp = out_path + ".raw.mp4"
    writer = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    strike_frames = {}
    for s in per_strike:
        for f in range(s["frame"] - 1, s["frame"] + int(0.12 * fps) + 1):
            strike_frames.setdefault(f, s)

    names = ["nose", None, None, None, None, None, None, None, None, None, None,
             "l_sh", "r_sh", "l_el", "r_el", "l_wr", "r_wr", None, None, None,
             None, None, None, "l_hip", "r_hip", "l_knee", "r_knee",
             "l_ankle", "r_ankle", "l_heel", "r_heel", "l_foot", "r_foot"]

    def pt(name, f):
        return int(round(S[name][0][f])), int(round(S[name][1][f]))

    i = 0
    while i < n:
        ok, frame = cap.read()
        if not ok:
            break
        fh, fw = frame.shape[:2]
        if (fw, fh) != (w, h):
            frame = cv2.resize(frame, (w, h))

        if not np.isnan(lm[i, NOSE, 0]):
            for a, b in SKELETON:
                if names[a] and names[b]:
                    cv2.line(frame, pt(names[a], i), pt(names[b], i),
                             (80, 255, 80), 2, cv2.LINE_AA)
            for nm in names:
                if nm:
                    cv2.circle(frame, pt(nm, i), 4, (0, 90, 255), -1, cv2.LINE_AA)

        # HUD
        lean = math.degrees(math.atan2(
            metrics["direction"] * ((S["l_sh"][0][i] + S["r_sh"][0][i]) / 2 -
                                    (S["l_hip"][0][i] + S["r_hip"][0][i]) / 2),
            ((S["l_hip"][1][i] + S["r_hip"][1][i]) / 2 -
             (S["l_sh"][1][i] + S["r_sh"][1][i]) / 2) + 1e-9))
        if metrics["view"] == "frontal":
            obliq = math.degrees(math.atan2(
                S["r_hip"][1][i] - S["l_hip"][1][i],
                abs(S["r_hip"][0][i] - S["l_hip"][0][i]) + 1e-9))
            second = f"pelvis tilt {obliq:+.0f} deg"
        else:
            second = f"trunk lean {lean:+.0f} deg"
        hud = [f"cadence {metrics['cadence']:.0f} spm",
               second,
               f"{metrics['view']} view · t = {i / fps:.2f} s"]
        box_h = 22 * len(hud) + 14
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (290, 10 + box_h), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.55, frame, 0.45, 0)
        for j, line in enumerate(hud):
            cv2.putText(frame, line, (20, 34 + 22 * j),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
                        cv2.LINE_AA)

        s = strike_frames.get(i)
        if s is not None:
            ankle = "l_ankle" if s["side"] == "L" else "r_ankle"
            cv2.circle(frame, pt(ankle, i), 14, (0, 220, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, f"{s['side']} strike ({s['type']})",
                        (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (0, 220, 255), 2, cv2.LINE_AA)

        writer.write(frame)
        i += 1
        if progress:
            progress(0.75 + 0.2 * (i / n))
    cap.release()
    writer.release()

    # Transcode to browser-playable H.264
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-i", tmp, "-c:v", "libx264", "-preset", "fast",
             "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             "-an", out_path],
            check=True, capture_output=True)
        os.remove(tmp)
    except Exception:
        os.replace(tmp, out_path)  # fall back to mp4v file
    if progress:
        progress(1.0)


def analyze(video_path, out_video_path, height_cm=None, progress=None):
    """Full pipeline. Returns dict with metrics, feedback cards, chart data."""
    lm, fps, size, _ = extract_landmarks(video_path, progress)
    metrics, per_strike, chart, S = compute_metrics(lm, fps, size, height_cm)
    render_annotated(video_path, out_video_path, lm, S, metrics, per_strike,
                     fps, size, progress)
    feedback = build_feedback(metrics)
    # Distinct studies actually cited in this report, for a References section.
    seen, refs = set(), []
    for f in feedback:
        s = f["source"]
        if s and s["cite"] not in seen:
            seen.add(s["cite"])
            refs.append(s)
    return {"metrics": metrics, "feedback": feedback, "chart": chart,
            "references": refs, "strikes": per_strike}


def _selfcheck():
    """Synthetic frontal-view runner with a known ~8° pelvic drop → assert the
    view classifier and pelvic-drop math. Also checks Altman–Davis FSA cutoffs."""
    fps, secs, w, h = 30.0, 6, 640, 480
    n = int(fps * secs)
    lm = np.zeros((n, 33, 3))
    A = 6.3  # hip y amplitude → atan2(2A, 90px hip width) ≈ 8°
    for i in range(n):
        t = i / fps
        s = math.sin(2 * math.pi * 1.5 * t)
        P = {NOSE: (320, 120), L_SHOULDER: (380, 180), R_SHOULDER: (260, 180),
             L_ELBOW: (395, 250), R_ELBOW: (245, 250),
             L_WRIST: (400, 315), R_WRIST: (240, 315),
             L_HIP: (365, 280 + A * s), R_HIP: (275, 280 - A * s),
             L_KNEE: (360, 380), R_KNEE: (280, 380),
             L_ANKLE: (358, 460 + 10 * s), R_ANKLE: (282, 460 - 10 * s),
             L_HEEL: (356, 465 + 10 * s), R_HEEL: (284, 465 - 10 * s),
             L_FOOT: (366, 470 + 10 * s), R_FOOT: (274, 470 - 10 * s)}
        for idx in range(33):
            x, y = P.get(idx, (320, 240))
            lm[i, idx] = (x, y, 0.9)

    m, _, _, _ = compute_metrics(lm, fps, (w, h))
    assert m["view"] == "frontal", f"view={m['view']} ratio={m['view_ratio']:.2f}"
    assert 6 <= m["pelvic_drop_deg"] <= 10, f"cpd={m['pelvic_drop_deg']:.1f}"

    # Altman–Davis foot-strike-angle cutoffs (>8 rear, <-1.6 fore, else mid)
    def classify(fsa):
        return "heel" if fsa > 8 else "forefoot" if fsa < -1.6 else "midfoot"
    assert classify(12) == "heel" and classify(-5) == "forefoot" \
        and classify(3) == "midfoot"
    print(f"selfcheck OK · view=frontal · pelvic_drop={m['pelvic_drop_deg']:.1f}°")


if __name__ == "__main__":
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="Analyze running form from a video.")
    ap.add_argument("video", nargs="?")
    ap.add_argument("--selfcheck", action="store_true",
                    help="run the built-in synthetic self-check and exit")
    ap.add_argument("-o", "--out", default=None,
                    help="annotated video path (default: <video>_annotated.mp4)")
    ap.add_argument("--height", type=float, default=None,
                    help="runner height in cm (enables bounce estimate in cm)")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        raise SystemExit(0)
    if not args.video:
        ap.error("a video path is required (or use --selfcheck)")
    out = args.out or os.path.splitext(args.video)[0] + "_annotated.mp4"

    res = analyze(args.video, out, height_cm=args.height,
                  progress=lambda p: print(f"\r{p * 100:5.1f}%", end="", flush=True))
    print()
    m = res["metrics"]
    icons = {"good": "✅", "info": "ℹ️ ", "warn": "⚠️ "}
    print(f"\n{m['view']} view · {m['n_steps']} steps over {m['duration_s']:.1f}s\n")
    for f in res["feedback"]:
        print(f"{icons[f['status']]} {f['title']} — {f['value']}")
        print(f"   {f['message']}")
        if f["source"]:
            print(f"   ↳ {f['source']['cite']}")
        print()
    for w in m["warnings"]:
        print("⚠️ ", w)
    json_path = os.path.splitext(out)[0] + ".json"
    with open(json_path, "w") as fh:
        _json.dump(res, fh, indent=1)
    print(f"Annotated video: {out}\nFull metrics:    {json_path}")

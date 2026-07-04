// FormAnalyzer.swift — running-form metrics from pose landmarks.
//
// Pure Foundation (no MediaPipe / UIKit / SwiftUI) so it compiles and runs
// standalone — see ios/selfcheck.sh. This is a direct port of analyzer.py's
// compute_metrics + build_feedback. Landmarks arrive as pixel coordinates
// (33 MediaPipe points per frame); VideoAnalyzer converts the SDK's normalized
// output to pixels before calling analyze().
//
// ponytail: smoothing is a centered moving average, not the Savitzky–Golay
// filter the Python uses — a few % noisier, far less code. Swap in a proper
// SG filter only if the numbers look jittery on real clips.

import Foundation

// MARK: - Landmark indices (MediaPipe Pose, 33 points)

enum LM {
    static let nose = 0
    static let lShoulder = 11, rShoulder = 12
    static let lElbow = 13, rElbow = 14
    static let lWrist = 15, rWrist = 16
    static let lHip = 23, rHip = 24
    static let lKnee = 25, rKnee = 26
    static let lAnkle = 27, rAnkle = 28
    static let lHeel = 29, rHeel = 30
    static let lFoot = 31, rFoot = 32
}

struct Landmark {
    var x: Double   // pixels
    var y: Double   // pixels (top-left origin, y down)
    var v: Double   // visibility 0…1
}

enum RunView: String { case sagittal, frontal }

struct Citation: Codable, Hashable {
    let cite: String
    let note: String
    let url: String
}

struct FeedbackCard: Identifiable {
    let id = UUID()
    let status: String   // "good" | "info" | "warn"
    let title: String
    let value: String
    let message: String
    let source: Citation?
}

struct FormMetrics {
    var view: RunView
    var cadence: Double
    var nSteps: Int
    var durationS: Double
    var trunkLeanDeg: Double
    var shinAngleDeg: Double
    var footReachLegs: Double
    var kneeAngleAtStrike: Double
    var footStrikeType: String
    var footStrikeCounts: [String: Int]
    var footStrikeAngleDeg: Double
    var pelvicDropDeg: Double
    var strideWidthRatio: Double
    var voPctLeg: Double
    var voCm: Double?
    var symmetryPct: Double?
    var elbowAngle: Double?
    var warnings: [String]
}

struct FormReport {
    let metrics: FormMetrics
    let feedback: [FeedbackCard]
    let references: [Citation]
    let ankleTrace: (t: [Double], left: [Double], right: [Double])
    let strikeTimes: [(t: Double, side: String)]
}

enum AnalysisError: Error, LocalizedError {
    case tooFewStrikes(Int)
    case noPerson(Double)
    var errorDescription: String? {
        switch self {
        case .tooFewStrikes(let n):
            return "Only \(n) foot strikes were detected — the clip is too short or the "
                + "legs aren't clearly visible. Use a 5–15 s clip of continuous running."
        case .noPerson(let frac):
            return "A person was only detected in \(Int(frac * 100))% of frames. Make sure "
                + "the runner is clearly visible and fills a good part of the frame."
        }
    }
}

// MARK: - Citations (the studies each card is grounded in)

enum Refs {
    static let heiderscheit = Citation(
        cite: "Heiderscheit et al. 2011, Med Sci Sports Exerc",
        note: "+5–10% step rate cut knee energy absorption 20–34% and reduced vertical "
            + "COM excursion and step length.",
        url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC3022995/")
    static let altman = Citation(
        cite: "Altman & Davis 2012, Gait & Posture",
        note: "Foot-strike angle cutoffs: >8° rearfoot, −1.6–8° midfoot, <−1.6° forefoot.",
        url: "https://pmc.ncbi.nlm.nih.gov/articles/PMC3278526/")
    static let folland = Citation(
        cite: "Folland et al. 2017, Med Sci Sports Exerc",
        note: "Pelvis vertical oscillation was the kinematic variable most strongly "
            + "related to running economy (r=0.53); lower is better.",
        url: "https://pubmed.ncbi.nlm.nih.gov/28263283/")
    static let bramah = Citation(
        cite: "Bramah et al. 2018, Am J Sports Med",
        note: "Injured runners showed greater contralateral pelvic drop, greater forward "
            + "trunk lean, and a more extended knee at contact. Pelvic drop was the "
            + "strongest predictor — each 1° raised injury odds ~80%.",
        url: "https://journals.sagepub.com/doi/full/10.1177/0363546518793657")
    static let teng = Citation(
        cite: "Teng & Powers 2014, JOSPT",
        note: "Greater forward trunk flexion lowered patellofemoral joint stress; too "
            + "upright raises knee load.",
        url: "https://www.jospt.org/doi/10.2519/jospt.2014.5575")
}

// MARK: - Small numeric helpers

enum Num {
    static func median(_ a: [Double]) -> Double {
        guard !a.isEmpty else { return 0 }
        let s = a.sorted()
        let m = s.count / 2
        return s.count % 2 == 0 ? (s[m - 1] + s[m]) / 2 : s[m]
    }

    static func percentile(_ a: [Double], _ p: Double) -> Double {
        guard !a.isEmpty else { return 0 }
        let s = a.sorted()
        let idx = p / 100 * Double(s.count - 1)
        let lo = Int(idx.rounded(.down)), hi = Int(idx.rounded(.up))
        if lo == hi { return s[lo] }
        return s[lo] + (s[hi] - s[lo]) * (idx - Double(lo))
    }

    static func mean(_ a: [Double]) -> Double { a.isEmpty ? 0 : a.reduce(0, +) / Double(a.count) }

    static func std(_ a: [Double]) -> Double {
        guard a.count > 1 else { return 0 }
        let m = mean(a)
        return (a.reduce(0) { $0 + ($1 - m) * ($1 - m) } / Double(a.count)).squareRoot()
    }

    /// Centered moving average with an odd window.
    static func smooth(_ a: [Double], _ window: Int) -> [Double] {
        let w = max(3, window | 1)
        guard a.count > w else { return a }
        let half = w / 2
        var out = a
        for i in 0..<a.count {
            let lo = max(0, i - half), hi = min(a.count - 1, i + half)
            var s = 0.0
            for j in lo...hi { s += a[j] }
            out[i] = s / Double(hi - lo + 1)
        }
        return out
    }

    /// Angle ABC in degrees at vertex b.
    static func angle(_ b: (Double, Double), _ a: (Double, Double),
                      _ c: (Double, Double)) -> Double {
        let v1 = (a.0 - b.0, a.1 - b.1), v2 = (c.0 - b.0, c.1 - b.1)
        let dot = v1.0 * v2.0 + v1.1 * v2.1
        let n = (hypot(v1.0, v1.1) * hypot(v2.0, v2.1)) + 1e-9
        return acos(max(-1, min(1, dot / n))) * 180 / .pi
    }

    /// Local maxima of `y`, at least `minDist` apart, above a prominence floor.
    static func findPeaks(_ y: [Double], minDist: Int, prominence: Double) -> [Int] {
        var cands: [Int] = []
        for i in 1..<(y.count - 1) where y[i] >= y[i - 1] && y[i] >= y[i + 1] {
            cands.append(i)
        }
        // prominence: peak minus the higher of its neighbouring valleys (approx via window)
        let base = median(y)
        cands = cands.filter { y[$0] >= base + prominence }
        // greedily enforce min distance, keeping the tallest
        var kept: [Int] = []
        for i in cands.sorted(by: { y[$0] > y[$1] }) {
            if kept.allSatisfy({ abs($0 - i) >= minDist }) { kept.append(i) }
        }
        return kept.sorted()
    }
}

// MARK: - Analyzer

enum FormAnalyzer {

    /// `frames`: n × 33 landmarks (pixels). `size`: (width, height) px.
    static func analyze(frames: [[Landmark]], fps: Double, size: (w: Double, h: Double),
                        heightCm: Double?) throws -> FormReport {
        let n = frames.count
        var warnings: [String] = []

        let detected = frames.map { $0[LM.nose].x.isFinite && $0[LM.nose].v > 0 ? 1.0 : 0.0 }
        let detFrac = Num.mean(detected.isEmpty ? [0] : detected)
        // MediaPipe fills positions even when occluded; a near-empty result means no runner.
        let anyVis = Num.mean(frames.map { Num.mean($0.map(\.v)) })
        if anyVis < 0.15 { throw AnalysisError.noPerson(anyVis) }
        _ = detFrac

        // Smoothed pixel series per joint.
        let win = Int((fps * 0.08).rounded())
        func series(_ idx: Int, _ axis: Int) -> [Double] {
            Num.smooth(frames.map { axis == 0 ? $0[idx].x : $0[idx].y }, win)
        }
        var X: [Int: [Double]] = [:], Y: [Int: [Double]] = [:], V: [Int: Double] = [:]
        let joints = [LM.nose, LM.lShoulder, LM.rShoulder, LM.lElbow, LM.rElbow,
                      LM.lWrist, LM.rWrist, LM.lHip, LM.rHip, LM.lKnee, LM.rKnee,
                      LM.lAnkle, LM.rAnkle, LM.lHeel, LM.rHeel, LM.lFoot, LM.rFoot]
        for j in joints {
            X[j] = series(j, 0); Y[j] = series(j, 1)
            V[j] = Num.mean(frames.map { $0[j].v })
        }

        let midHipX = zip(X[LM.lHip]!, X[LM.rHip]!).map { ($0 + $1) / 2 }
        let midHipY = zip(Y[LM.lHip]!, Y[LM.rHip]!).map { ($0 + $1) / 2 }
        let midShX = zip(X[LM.lShoulder]!, X[LM.rShoulder]!).map { ($0 + $1) / 2 }
        let midShY = zip(Y[LM.lShoulder]!, Y[LM.rShoulder]!).map { ($0 + $1) / 2 }

        // Direction of travel (+1 = moving right). Fall back to foot orientation.
        let hipDisp = (midHipX.last! - midHipX.first!)
        let direction: Double
        if abs(hipDisp) > 0.05 * size.w {
            direction = hipDisp > 0 ? 1 : -1
        } else {
            let toeHeel = Num.median(zip(X[LM.lFoot]!, X[LM.lHeel]!).map { $0 - $1 }
                + zip(X[LM.rFoot]!, X[LM.rHeel]!).map { $0 - $1 })
            direction = toeHeel >= 0 ? 1 : -1
        }

        // Body scale: mean leg length (hip→knee→ankle) in px.
        func seg(_ a: Int, _ b: Int) -> [Double] {
            (0..<n).map { hypot(X[a]![$0] - X[b]![$0], Y[a]![$0] - Y[b]![$0]) }
        }
        let legEach = (0..<n).map { i -> Double in
            (seg(LM.lHip, LM.lKnee)[i] + seg(LM.lKnee, LM.lAnkle)[i]
                + seg(LM.rHip, LM.rKnee)[i] + seg(LM.rKnee, LM.rAnkle)[i]) / 2
        }
        let legPx = Num.median(legEach)
        let pxPerCm = heightCm.map { legPx / (0.49 * $0) }

        // Camera view.
        let shoulderW = Num.median((0..<n).map { abs(X[LM.lShoulder]![$0] - X[LM.rShoulder]![$0]) })
        let torsoH = Num.median((0..<n).map { abs(midShY[$0] - midHipY[$0]) }) + 1e-9
        let view: RunView = (shoulderW / torsoH) > 0.62 ? .frontal : .sagittal

        // Pelvic obliquity (frontal plane), signed deg off horizontal.
        let pelvisObliq = (0..<n).map {
            atan2(Y[LM.rHip]![$0] - Y[LM.lHip]![$0],
                  abs(X[LM.rHip]![$0] - X[LM.lHip]![$0]) + 1e-9) * 180 / .pi
        }

        // Foot strikes: ankle at its lowest point (max y).
        let minDist = max(3, Int(0.45 * fps))
        func strikes(_ ankle: Int) -> [Int] {
            let y = Y[ankle]!
            let rng = Num.percentile(y, 95) - Num.percentile(y, 5)
            return Num.findPeaks(y, minDist: minDist, prominence: max(2.0, 0.12 * rng))
        }
        let lStrikes = strikes(LM.lAnkle), rStrikes = strikes(LM.rAnkle)
        let allStrikes = (lStrikes.map { ($0, "L") } + rStrikes.map { ($0, "R") })
            .sorted { $0.0 < $1.0 }
        if allStrikes.count < 4 { throw AnalysisError.tooFewStrikes(allStrikes.count) }
        if allStrikes.count < 8 {
            warnings.append("Only \(allStrikes.count) steps detected; metrics are rough "
                + "averages. A 10+ second clip is more reliable.")
        }

        // Cadence.
        let span = Double(allStrikes.last!.0 - allStrikes.first!.0) / fps
        let cadence = 60.0 * Double(allStrikes.count - 1) / span

        // Symmetry.
        var symmetry: Double?
        if lStrikes.count >= 2 && rStrikes.count >= 2 {
            let li = Num.median(zip(lStrikes.dropFirst(), lStrikes).map { Double($0 - $1) })
            let ri = Num.median(zip(rStrikes.dropFirst(), rStrikes).map { Double($0 - $1) })
            symmetry = abs(li - ri) / ((li + ri) / 2) * 100
        }

        // Per-strike measurements.
        var shins: [Double] = [], knees: [Double] = [], reaches: [Double] = [], fsas: [Double] = []
        var counts: [String: Int] = [:]
        for (f, side) in allStrikes {
            let p = side == "L"
            let hip = p ? (X[LM.lHip]![f], Y[LM.lHip]![f]) : (X[LM.rHip]![f], Y[LM.rHip]![f])
            let knee = p ? (X[LM.lKnee]![f], Y[LM.lKnee]![f]) : (X[LM.rKnee]![f], Y[LM.rKnee]![f])
            let ankle = p ? (X[LM.lAnkle]![f], Y[LM.lAnkle]![f]) : (X[LM.rAnkle]![f], Y[LM.rAnkle]![f])
            let heel = p ? (X[LM.lHeel]![f], Y[LM.lHeel]![f]) : (X[LM.rHeel]![f], Y[LM.rHeel]![f])
            let toe = p ? (X[LM.lFoot]![f], Y[LM.lFoot]![f]) : (X[LM.rFoot]![f], Y[LM.rFoot]![f])
            knees.append(Num.angle(knee, hip, ankle))
            shins.append(atan2(direction * (ankle.0 - knee.0), ankle.1 - knee.1 + 1e-9) * 180 / .pi)
            reaches.append(direction * (ankle.0 - hip.0) / legPx)
            let footLen = hypot(toe.0 - heel.0, toe.1 - heel.1) + 1e-9
            let fsa = asin(max(-1, min(1, (heel.1 - toe.1) / footLen))) * 180 / .pi
            fsas.append(fsa)
            let type = fsa > 8 ? "heel" : (fsa < -1.6 ? "forefoot" : "midfoot")
            counts[type, default: 0] += 1
        }
        let dominant = counts.max { $0.value < $1.value }!.key

        // Contralateral pelvic drop & stride width (frontal-plane).
        let obMed = Num.median(pelvisObliq)
        let cpd = Num.percentile(pelvisObliq.map { abs($0 - obMed) }, 95)
        let hipW = Num.median((0..<n).map { abs(X[LM.lHip]![$0] - X[LM.rHip]![$0]) }) + 1e-9
        let strideWidth = Num.median(allStrikes.map { abs(X[LM.lAnkle]![$0.0] - X[LM.rAnkle]![$0.0]) }) / hipW

        // Trunk lean.
        let leanSeries = (0..<n).map {
            atan2(direction * (midShX[$0] - midHipX[$0]), midHipY[$0] - midShY[$0] + 1e-9) * 180 / .pi
        }
        let trunkLean = Num.median(leanSeries)

        // Vertical oscillation of the hips.
        let trend = Num.smooth(midHipY, max(5, Int((fps * 1.2).rounded())))
        let osc = zip(midHipY, trend).map { $0 - $1 }
        let sf = allStrikes.map { $0.0 }
        var ptp: [Double] = []
        for (a, b) in zip(sf, sf.dropFirst()) where b - a > 2 {
            let seg = Array(osc[a...b])
            ptp.append(seg.max()! - seg.min()!)
        }
        let voPx = ptp.isEmpty ? (osc.max()! - osc.min()!) : Num.median(ptp)
        let voPctLeg = voPx / legPx * 100
        let voCm = pxPerCm.map { voPx / $0 }

        // Arm carry (median elbow angle).
        var elbowAngles: [Double] = []
        for (sh, el, wr) in [(LM.lShoulder, LM.lElbow, LM.lWrist),
                             (LM.rShoulder, LM.rElbow, LM.rWrist)] where V[wr]! > 0.5 {
            for f in stride(from: 0, to: n, by: 2) {
                elbowAngles.append(Num.angle((X[el]![f], Y[el]![f]),
                                             (X[sh]![f], Y[sh]![f]), (X[wr]![f], Y[wr]![f])))
            }
        }
        let elbow = elbowAngles.isEmpty ? nil : Num.median(elbowAngles)

        if Num.mean([LM.lHip, LM.rHip, LM.lKnee, LM.rKnee, LM.lAnkle, LM.rAnkle].map { V[$0]! }) < 0.45 {
            warnings.append("Hips/legs were often obscured — film with the whole body in frame.")
        }

        let m = FormMetrics(
            view: view, cadence: cadence, nSteps: allStrikes.count, durationS: Double(n) / fps,
            trunkLeanDeg: trunkLean, shinAngleDeg: Num.median(shins),
            footReachLegs: Num.median(reaches), kneeAngleAtStrike: Num.median(knees),
            footStrikeType: dominant, footStrikeCounts: counts,
            footStrikeAngleDeg: Num.median(fsas), pelvicDropDeg: cpd,
            strideWidthRatio: strideWidth, voPctLeg: voPctLeg, voCm: voCm,
            symmetryPct: symmetry, elbowAngle: elbow, warnings: warnings)

        let feedback = buildFeedback(m)
        var seen = Set<String>(), refs: [Citation] = []
        for c in feedback.compactMap(\.source) where !seen.contains(c.cite) {
            seen.insert(c.cite); refs.append(c)
        }
        let step = max(1, n / 600)
        let trace = (t: stride(from: 0, to: n, by: step).map { Double($0) / fps },
                     left: stride(from: 0, to: n, by: step).map { size.h - Y[LM.lAnkle]![$0] },
                     right: stride(from: 0, to: n, by: step).map { size.h - Y[LM.rAnkle]![$0] })
        let strikeTimes = allStrikes.map { (t: Double($0.0) / fps, side: $0.1) }
        return FormReport(metrics: m, feedback: feedback, references: refs,
                          ankleTrace: trace, strikeTimes: strikeTimes)
    }

    // MARK: - Feedback (view-aware, cited)

    static func buildFeedback(_ m: FormMetrics) -> [FeedbackCard] {
        var fb: [FeedbackCard] = []
        let frontal = m.view == .frontal

        let c = m.cadence
        if c < 160 {
            fb.append(.init(status: "warn", title: "Cadence", value: "\(Int(c)) spm",
                message: "On the low side. Heiderscheit et al. found raising step rate 5–10% "
                    + "cut energy absorbed at the knee by 20–34%. Nudge it up ~5% with a "
                    + "metronome — quicker, lighter steps.", source: Refs.heiderscheit))
        } else if c <= 190 {
            fb.append(.init(status: "good", title: "Cadence", value: "\(Int(c)) spm",
                message: "In the range where the foot lands near the body. No change needed.",
                source: Refs.heiderscheit))
        } else {
            fb.append(.init(status: "info", title: "Cadence", value: "\(Int(c)) spm",
                message: "Quite high — fine for a fast interval or a smaller runner.",
                source: Refs.heiderscheit))
        }

        let voStr = m.voCm.map { String(format: "%.1f cm (est.)", $0) }
            ?? String(format: "%.1f%% of leg", m.voPctLeg)
        let hi = m.voCm.map { $0 > 10.5 } ?? (m.voPctLeg > 13)
        let mid = m.voCm.map { $0 > 8.5 } ?? (m.voPctLeg > 10)
        if hi {
            fb.append(.init(status: "warn", title: "Vertical oscillation", value: voStr,
                message: "Noticeable bounce. Folland et al. found vertical oscillation was the "
                    + "movement variable most tied to running economy. Higher cadence and a "
                    + "level gaze reduce it.", source: Refs.folland))
        } else if mid {
            fb.append(.init(status: "info", title: "Vertical oscillation", value: voStr,
                message: "A bit of bounce, within normal range.", source: Refs.folland))
        } else {
            fb.append(.init(status: "good", title: "Vertical oscillation", value: voStr,
                message: "Low bounce — energy going into forward motion.", source: Refs.folland))
        }

        if frontal {
            let cpd = m.pelvicDropDeg
            if cpd > 10 {
                fb.append(.init(status: "warn", title: "Pelvic drop",
                    value: String(format: "%.1f° peak", cpd),
                    message: "Your hip drops noticeably on the swing side. Bramah et al. found "
                        + "this the strongest gait predictor of injury — each 1° raised odds "
                        + "~80%. Hip-stability work (side planks, single-leg) helps.",
                    source: Refs.bramah))
            } else if cpd > 5 {
                fb.append(.init(status: "info", title: "Pelvic drop",
                    value: String(format: "%.1f° peak", cpd),
                    message: "A mild hip drop on the swing side. Worth watching; hip-stability "
                        + "work keeps it in check.", source: Refs.bramah))
            } else {
                fb.append(.init(status: "good", title: "Pelvic drop",
                    value: String(format: "%.1f° peak", cpd),
                    message: "Pelvis stays level through stance — strong hip stability.",
                    source: Refs.bramah))
            }
            let sw = m.strideWidthRatio
            if sw < 1.0 {
                fb.append(.init(status: "warn", title: "Crossover / stride width",
                    value: String(format: "gap %.1f× hip", sw),
                    message: "Feet land close to (or across) the midline — a crossover gait "
                        + "linked to ITB and knee pain. Land on 'two rails', not a tightrope.",
                    source: Refs.bramah))
            } else {
                fb.append(.init(status: "good", title: "Crossover / stride width",
                    value: String(format: "gap %.1f× hip", sw),
                    message: "Feet land in two parallel lines — no crossover.", source: Refs.bramah))
            }
        } else {
            let shin = m.shinAngleDeg, reach = m.footReachLegs
            if shin > 8 || reach > 0.28 {
                fb.append(.init(status: "warn", title: "Overstriding",
                    value: String(format: "shin %.0f° at contact", shin),
                    message: "Your foot lands ahead of your body with the shin angled forward — "
                        + "a braking overstride. Quicker cadence brings it under your hips.",
                    source: Refs.heiderscheit))
            } else if shin > 4 {
                fb.append(.init(status: "info", title: "Foot landing",
                    value: String(format: "shin %.0f° at contact", shin),
                    message: "Mild reach in front of the body — worth changing only if you get "
                        + "shin or knee niggles.", source: Refs.heiderscheit))
            } else {
                fb.append(.init(status: "good", title: "Foot landing",
                    value: String(format: "shin %.0f° at contact", shin),
                    message: "Foot lands under your center of mass with a near-vertical shin.",
                    source: Refs.heiderscheit))
            }

            let dist = m.footStrikeCounts.sorted { $0.value > $1.value }
                .map { "\($0.value)× \($0.key)" }.joined(separator: ", ")
            let val = String(format: "mostly %@ · %+.0f° (%@)", m.footStrikeType,
                             m.footStrikeAngleDeg, dist)
            if m.footStrikeType == "heel" && (shin > 8 || reach > 0.28) {
                fb.append(.init(status: "warn", title: "Foot strike", value: val,
                    message: "By the Altman–Davis foot-strike angle you're a heel-striker, and "
                        + "with the overstride above that amplifies braking. Fix the overstride "
                        + "first — don't force a forefoot landing.", source: Refs.altman))
            } else {
                let label: String
                switch m.footStrikeType {
                case "heel": label = "Heel-striking with the foot under you is fine — most elite "
                    + "marathoners do it."
                case "forefoot": label = "A forefoot landing — fine if natural; watch calf/Achilles "
                    + "tightness with volume."
                default: label = "A midfoot landing — nothing to change."
                }
                fb.append(.init(status: "good", title: "Foot strike", value: val,
                    message: label + " (Altman–Davis foot-strike angle.)", source: Refs.altman))
            }

            let ka = m.kneeAngleAtStrike
            if ka > 172 {
                fb.append(.init(status: "warn", title: "Knee at landing",
                    value: String(format: "%.0f° (nearly straight)", ka),
                    message: "You land on an almost straight leg. Bramah et al. found injured "
                        + "runners contacted with a more extended knee — a stiff leg passes "
                        + "impact to the joints.", source: Refs.bramah))
            } else {
                fb.append(.init(status: "good", title: "Knee at landing",
                    value: String(format: "%.0f°", ka),
                    message: "Soft knee at contact — muscles absorb the impact.", source: Refs.bramah))
            }

            let lean = m.trunkLeanDeg
            if lean < 1 {
                fb.append(.init(status: "warn", title: "Trunk lean",
                    value: String(format: "%.1f°", lean),
                    message: "You run very upright. Teng & Powers found more forward trunk flexion "
                        + "lowers kneecap stress; too upright brakes the stride. Lean from the "
                        + "ankles, not the waist.", source: Refs.teng))
            } else if lean <= 12 {
                fb.append(.init(status: "good", title: "Trunk lean",
                    value: String(format: "%.1f° forward", lean),
                    message: "A comfortable forward lean — eases knee load without overloading "
                        + "the back.", source: Refs.teng))
            } else {
                fb.append(.init(status: "warn", title: "Trunk lean",
                    value: String(format: "%.1f° forward", lean),
                    message: "A lot of forward lean — often bending at the waist, which Bramah "
                        + "linked to injury. Run tall, lean from the ankles.", source: Refs.bramah))
            }
        }

        if let s = m.symmetryPct {
            if s > 8 {
                fb.append(.init(status: "warn", title: "L/R symmetry",
                    value: String(format: "%.0f%% difference", s),
                    message: "Left and right step timing differ. Can be camera noise, but if "
                        + "consistent it's worth a physio look.", source: nil))
            } else {
                fb.append(.init(status: "good", title: "L/R symmetry",
                    value: String(format: "%.0f%% difference", s),
                    message: "Left and right step timing are well matched.", source: nil))
            }
        }
        if let e = m.elbowAngle {
            if e > 115 {
                fb.append(.init(status: "info", title: "Arm carry",
                    value: String(format: "elbow %.0f°", e),
                    message: "Arms carried fairly straight/low. Bending nearer ~90° keeps the "
                        + "swing compact.", source: nil))
            } else if e < 60 {
                fb.append(.init(status: "info", title: "Arm carry",
                    value: String(format: "elbow %.0f°", e),
                    message: "Arms quite tightly bent/high — keep shoulders relaxed.", source: nil))
            } else {
                fb.append(.init(status: "good", title: "Arm carry",
                    value: String(format: "elbow %.0f°", e),
                    message: "Elbow bend is in a relaxed, efficient range.", source: nil))
            }
        }

        let order = ["warn": 0, "info": 1, "good": 2]
        return fb.sorted { order[$0.status]! < order[$1.status]! }
    }
}

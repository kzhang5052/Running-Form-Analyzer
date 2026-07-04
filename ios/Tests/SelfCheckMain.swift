// Standalone self-check for the ported metric math — compiles with the Command
// Line Tools swift (no Xcode/MediaPipe needed). Run via ios/selfcheck.sh.
// Mirrors analyzer.py's _selfcheck: a synthetic frontal runner with a known
// ~8° pelvic drop.
import Foundation

func makeFrontalRunner() -> [[Landmark]] {
    let fps = 30.0, secs = 8
    let n = Int(fps) * secs
    let A = 6.3  // hip-y amplitude → atan2(2A, 90px) ≈ 8°
    var frames: [[Landmark]] = []
    for i in 0..<n {
        let t = Double(i) / fps
        let s = sin(2 * .pi * 1.5 * t)
        let pts: [(Int, Double, Double)] = [
            (LM.nose, 320, 120), (LM.lShoulder, 380, 180), (LM.rShoulder, 260, 180),
            (LM.lElbow, 395, 250), (LM.rElbow, 245, 250), (LM.lWrist, 400, 315),
            (LM.rWrist, 240, 315), (LM.lHip, 365, 280 + A * s), (LM.rHip, 275, 280 - A * s),
            (LM.lKnee, 360, 380), (LM.rKnee, 280, 380), (LM.lAnkle, 358, 460 + 10 * s),
            (LM.rAnkle, 282, 460 - 10 * s), (LM.lHeel, 356, 465 + 10 * s),
            (LM.rHeel, 284, 465 - 10 * s), (LM.lFoot, 366, 470 + 10 * s),
            (LM.rFoot, 274, 470 - 10 * s),
        ]
        var frame = [Landmark](repeating: Landmark(x: 320, y: 240, v: 0.9), count: 33)
        for (idx, x, y) in pts { frame[idx] = Landmark(x: x, y: y, v: 0.9) }
        frames.append(frame)
    }
    return frames
}

func classify(_ fsa: Double) -> String { fsa > 8 ? "heel" : (fsa < -1.6 ? "forefoot" : "midfoot") }

@main
enum SelfCheck {
    static func main() throws {
        let report = try FormAnalyzer.analyze(frames: makeFrontalRunner(), fps: 30,
                                              size: (640, 480), heightCm: 183)
        let m = report.metrics
        precondition(m.view == .frontal, "view=\(m.view)")
        precondition(m.pelvicDropDeg >= 6 && m.pelvicDropDeg <= 10, "cpd=\(m.pelvicDropDeg)")
        precondition(classify(12) == "heel" && classify(-5) == "forefoot" && classify(3) == "midfoot")
        precondition(m.cadence > 150 && m.cadence < 210, "cadence=\(m.cadence)")
        precondition(!report.feedback.isEmpty
            && report.references.contains { $0.cite.contains("Bramah") })
        print(String(format: "selfcheck OK · view=frontal · pelvic_drop=%.1f° · cadence=%.0f · cards=%d",
                     m.pelvicDropDeg, m.cadence, report.feedback.count))
    }
}

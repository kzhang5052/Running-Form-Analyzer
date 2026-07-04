// VideoAnalyzer.swift — drives the whole pipeline for one video:
// extract frames (upright, capped at 30 s) → pose per frame → FormAnalyzer.
import Foundation
import AVFoundation
import CoreGraphics
import UIKit
import MediaPipeTasksVision

@MainActor
final class VideoAnalyzer: ObservableObject {
    enum State: Equatable { case idle, processing, done, failed(String) }

    @Published var state: State = .idle
    @Published var progress: Double = 0
    @Published var report: FormReport?

    private let maxSeconds = 30.0
    private let maxSide: CGFloat = 720   // downscale longest edge for speed

    func analyze(url: URL, heightCm: Double?) {
        state = .processing
        progress = 0
        report = nil
        Task.detached(priority: .userInitiated) { [weak self] in
            guard let self else { return }
            do {
                let result = try await self.run(url: url, heightCm: heightCm)
                await MainActor.run { self.report = result; self.state = .done; self.progress = 1 }
            } catch {
                await MainActor.run { self.state = .failed(error.localizedDescription) }
            }
        }
    }

    private func run(url: URL, heightCm: Double?) async throws -> FormReport {
        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .video).first
        else { throw NSError(domain: "FormCheck", code: 2,
                             userInfo: [NSLocalizedDescriptionKey: "No video track found."]) }

        let fpsRaw = try await track.load(.nominalFrameRate)
        let fps = (fpsRaw > 1 && fpsRaw <= 240) ? Double(fpsRaw) : 30.0
        let duration = try await asset.load(.duration).seconds
        let clip = min(duration, maxSeconds)
        let count = max(1, Int(clip * fps))

        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true   // upright regardless of rotation
        generator.requestedTimeToleranceBefore = CMTime(value: 1, timescale: Int32(fps * 2))
        generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: Int32(fps * 2))
        generator.maximumSize = CGSize(width: maxSide * 2, height: maxSide)

        let service = try PoseLandmarkerService()
        var frames: [[Landmark]] = []
        frames.reserveCapacity(count)
        var size: (w: Double, h: Double) = (0, 0)

        for i in 0..<count {
            let time = CMTime(seconds: Double(i) / fps, preferredTimescale: 600)
            guard let cg = try? generator.copyCGImage(at: time, actualTime: nil) else { continue }
            let scaled = downscale(cg, maxSide: maxSide)
            size = (Double(scaled.width), Double(scaled.height))
            let image = try MPImage(uiImage: UIImage(cgImage: scaled))
            let tsMs = Int(Double(i) * 1000.0 / fps)
            if let lm = service.landmarks(in: image, timestampMs: tsMs) {
                frames.append(lm)
            } else {
                // keep timeline aligned; a missing detection becomes a low-vis frame
                frames.append([Landmark](repeating: Landmark(x: 0, y: 0, v: 0), count: 33))
            }
            if i % 5 == 0 {
                let p = 0.9 * Double(i) / Double(count)
                await MainActor.run { self.progress = p }
            }
        }

        return try FormAnalyzer.analyze(frames: frames, fps: fps, size: size, heightCm: heightCm)
    }

    private func downscale(_ cg: CGImage, maxSide: CGFloat) -> CGImage {
        let w = CGFloat(cg.width), h = CGFloat(cg.height)
        let longest = max(w, h)
        guard longest > maxSide else { return cg }
        let scale = maxSide / longest
        let nw = Int(w * scale), nh = Int(h * scale)
        guard let ctx = CGContext(data: nil, width: nw, height: nh, bitsPerComponent: 8,
                                  bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return cg }
        ctx.interpolationQuality = .medium
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: nw, height: nh))
        return ctx.makeImage() ?? cg
    }
}

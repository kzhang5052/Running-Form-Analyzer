// PoseLandmarkerService.swift — thin wrapper over MediaPipe's on-device
// Pose Landmarker. Same model file as the Python app (bundled as a resource).
import Foundation
import MediaPipeTasksVision

final class PoseLandmarkerService {
    private let landmarker: PoseLandmarker

    init() throws {
        guard let path = Bundle.main.path(forResource: "pose_landmarker_full",
                                          ofType: "task") else {
            throw NSError(domain: "FormCheck", code: 1,
                          userInfo: [NSLocalizedDescriptionKey:
                            "pose_landmarker_full.task is missing from the app bundle."])
        }
        let options = PoseLandmarkerOptions()
        options.baseOptions.modelAssetPath = path
        options.runningMode = .video
        options.numPoses = 1
        options.minPoseDetectionConfidence = 0.5
        options.minTrackingConfidence = 0.5
        landmarker = try PoseLandmarker(options: options)
    }

    /// Detect the 33 pose landmarks in one video frame, returned in pixel
    /// coordinates. `timestampMs` must strictly increase across a clip.
    func landmarks(in image: MPImage, timestampMs: Int) -> [Landmark]? {
        guard let result = try? landmarker.detect(videoFrame: image,
                                                  timestampInMilliseconds: timestampMs),
              let pose = result.landmarks.first else { return nil }
        let w = Double(image.width), h = Double(image.height)
        return pose.map { lm in
            Landmark(x: Double(lm.x) * w, y: Double(lm.y) * h,
                     v: Double(truncating: lm.visibility ?? 0))
        }
    }
}

// ContentView.swift — pick a video, optionally enter height, analyze.
import SwiftUI
import PhotosUI
import CoreTransferable
import UniformTypeIdentifiers

/// A picked video copied into a temp file we can read frames from.
struct Movie: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let dir = FileManager.default.temporaryDirectory
            let copy = dir.appendingPathComponent("formcheck-\(UUID().uuidString).mov")
            try? FileManager.default.removeItem(at: copy)
            try FileManager.default.copyItem(at: received.file, to: copy)
            return Movie(url: copy)
        }
    }
}

struct ContentView: View {
    @StateObject private var analyzer = VideoAnalyzer()
    @State private var pick: PhotosPickerItem?
    @State private var videoURL: URL?
    @State private var height: String = ""
    @State private var loading = false

    var body: some View {
        ZStack {
            Color.ink.ignoresSafeArea()
            switch analyzer.state {
            case .processing:
                ProcessingView(progress: analyzer.progress)
            case .done:
                if let report = analyzer.report {
                    ReportView(report: report) { reset() }
                }
            case .failed(let msg):
                FailureView(message: msg) { reset() }
            case .idle:
                uploadScreen
            }
        }
    }

    private var uploadScreen: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("FORM/CHECK")
                    .font(.system(size: 26, weight: .heavy)).kerning(1)
                    .foregroundStyle(.fog)
                Text("Film the side. See the stride.")
                    .font(.system(size: 34, weight: .black)).foregroundStyle(.volt)
                Text("Pick 5–15 s of running. A side view reads stride, foot strike and "
                    + "posture; a front/rear view reads pelvic drop and crossover. The angle "
                    + "is detected automatically, on-device.")
                    .font(.system(size: 15)).foregroundStyle(.steel)

                PhotosPicker(selection: $pick, matching: .videos) {
                    HStack {
                        Image(systemName: videoURL == nil ? "square.and.arrow.up" : "checkmark.circle.fill")
                        Text(videoURL == nil ? "Choose a running video" : "Video ready — tap to change")
                    }
                    .font(.system(size: 16, weight: .semibold))
                    .frame(maxWidth: .infinity).padding(.vertical, 18)
                    .foregroundStyle(.fog)
                    .background(Color.panel)
                    .overlay(RoundedRectangle(cornerRadius: 4)
                        .stroke(videoURL == nil ? Color.line : Color.volt, lineWidth: 1))
                }

                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("HEIGHT (CM, OPTIONAL)").font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.steel)
                        TextField("183", text: $height)
                            .keyboardType(.numberPad)
                            .padding(10).background(Color.panel).foregroundStyle(.fog)
                            .frame(width: 120)
                    }
                    Spacer()
                }

                Button(action: start) {
                    Text(loading ? "Loading…" : "Analyze")
                        .font(.system(size: 17, weight: .bold))
                        .frame(maxWidth: .infinity).padding(.vertical, 15)
                        .background(videoURL == nil ? Color.steel : Color.volt)
                        .foregroundStyle(Color.ink)
                }
                .disabled(videoURL == nil || loading)

                Text("Everything runs on your iPhone — the video never leaves the device.")
                    .font(.system(size: 12)).foregroundStyle(.steel)
            }
            .padding(24)
        }
        .onChange(of: pick) { _, item in Task { await load(item) } }
    }

    private func load(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        loading = true
        defer { loading = false }
        if let movie = try? await item.loadTransferable(type: Movie.self) {
            videoURL = movie.url
        }
    }

    private func start() {
        guard let url = videoURL else { return }
        analyzer.analyze(url: url, heightCm: Double(height.trimmingCharacters(in: .whitespaces)))
    }

    private func reset() {
        analyzer.state = .idle
        analyzer.report = nil
        videoURL = nil
        pick = nil
    }
}

struct ProcessingView: View {
    let progress: Double
    var body: some View {
        VStack(spacing: 18) {
            Text("ANALYZING YOUR RUN").font(.system(size: 14, design: .monospaced))
                .foregroundStyle(.steel)
            Text("\(Int(progress * 100))%").font(.system(size: 44, weight: .bold))
                .foregroundStyle(.volt)
            ProgressView(value: progress).tint(.volt).frame(maxWidth: 260)
            Text("Detecting your pose frame by frame").font(.system(size: 13))
                .foregroundStyle(.steel)
        }.padding()
    }
}

struct FailureView: View {
    let message: String
    let onRetry: () -> Void
    var body: some View {
        VStack(spacing: 16) {
            Text("Couldn't read that run").font(.system(size: 24, weight: .bold))
                .foregroundStyle(.fog)
            Text(message).font(.system(size: 15)).foregroundStyle(.steel)
                .multilineTextAlignment(.center)
            Button("Try another video", action: onRetry)
                .font(.system(size: 16, weight: .bold)).padding(.horizontal, 24)
                .padding(.vertical, 12).background(Color.volt).foregroundStyle(Color.ink)
        }.padding(28)
    }
}

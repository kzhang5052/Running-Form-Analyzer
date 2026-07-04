// ReportView.swift — headline stats, cited coaching cards, references.
import SwiftUI

struct ReportView: View {
    let report: FormReport
    let onNew: () -> Void

    private var m: FormMetrics { report.metrics }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                statStrip
                findings
                if !report.references.isEmpty { references }
                Button("Analyze another video", action: onNew)
                    .font(.system(size: 16, weight: .bold)).frame(maxWidth: .infinity)
                    .padding(.vertical, 14).background(Color.volt).foregroundStyle(Color.ink)
                Text("Single-camera estimates are directional, not lab-grade. Compare clips "
                    + "filmed the same way, and see a professional if something hurts.")
                    .font(.system(size: 12)).foregroundStyle(.steel)
            }.padding(24)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(String(format: "%@ · %d steps over %.1fs",
                        m.view == .frontal ? "FRONT / REAR VIEW" : "SIDE VIEW",
                        m.nSteps, m.durationS))
                .font(.system(size: 11, design: .monospaced)).foregroundStyle(.steel)
            Text("STRIDE REPORT").font(.system(size: 32, weight: .black)).foregroundStyle(.fog)
            let counts = Dictionary(grouping: report.feedback, by: \.status).mapValues(\.count)
            HStack(spacing: 16) {
                Text("\(counts["warn"] ?? 0) fix").foregroundStyle(.warnAmber)
                Text("\(counts["info"] ?? 0) watch").foregroundStyle(.infoBlue)
                Text("\(counts["good"] ?? 0) good").foregroundStyle(.good)
            }.font(.system(size: 13, design: .monospaced))
        }
    }

    private var statStrip: some View {
        let stats: [(String, String)] = {
            var s: [(String, String)] = [("Cadence", "\(Int(m.cadence)) spm")]
            if m.view == .frontal {
                s.append(("Pelvic drop", String(format: "%.1f°", m.pelvicDropDeg)))
                s.append(("Stride width", String(format: "%.1f× hip", m.strideWidthRatio)))
            } else {
                s.append(("Foot strike", m.footStrikeType))
                s.append(("Shin @ contact", String(format: "%.0f°", m.shinAngleDeg)))
                s.append(("Trunk lean", String(format: "%.1f°", m.trunkLeanDeg)))
            }
            s.append(("Bounce", m.voCm.map { String(format: "%.1f cm", $0) }
                ?? String(format: "%.0f%% leg", m.voPctLeg)))
            if let sym = m.symmetryPct { s.append(("Symmetry Δ", String(format: "%.0f%%", sym))) }
            return s
        }()
        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 14) {
            ForEach(stats, id: \.0) { label, value in
                VStack(alignment: .leading, spacing: 2) {
                    Text(label.uppercased()).font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.steel)
                    Text(value).font(.system(size: 24, weight: .heavy)).foregroundStyle(.fog)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var findings: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("FINDINGS — WORST FIRST").font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.steel).padding(.bottom, 10)
            ForEach(report.feedback) { f in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text(f.status == "warn" ? "FIX" : f.status == "info" ? "WATCH" : "GOOD")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(Color.forStatus(f.status))
                        Text(f.title.uppercased()).font(.system(size: 16, weight: .bold))
                            .foregroundStyle(.fog)
                    }
                    Text(f.value).font(.system(size: 13, design: .monospaced)).foregroundStyle(.steel)
                    Text(f.message).font(.system(size: 14)).foregroundStyle(.fog.opacity(0.85))
                    if let src = f.source {
                        Link("↳ \(src.cite)", destination: URL(string: src.url)!)
                            .font(.system(size: 11, design: .monospaced)).foregroundStyle(.steel)
                    }
                }
                .padding(.leading, 12).padding(.vertical, 12)
                .overlay(Rectangle().frame(width: 2).foregroundStyle(Color.forStatus(f.status)),
                         alignment: .leading)
            }
        }
    }

    private var references: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("REFERENCES").font(.system(size: 11, design: .monospaced)).foregroundStyle(.steel)
            ForEach(report.references, id: \.cite) { r in
                VStack(alignment: .leading, spacing: 3) {
                    Link(r.cite, destination: URL(string: r.url)!)
                        .font(.system(size: 13, design: .monospaced)).foregroundStyle(.fog)
                    Text(r.note).font(.system(size: 13)).foregroundStyle(.steel)
                }.padding(.leading, 12)
                    .overlay(Rectangle().frame(width: 1).foregroundStyle(Color.line), alignment: .leading)
            }
        }
    }
}

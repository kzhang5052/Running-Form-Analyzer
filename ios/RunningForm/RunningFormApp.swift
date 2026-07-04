// RunningFormApp.swift — app entry + shared theme (matches the web "Form/Check").
import SwiftUI

@main
struct RunningFormApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView().preferredColorScheme(.dark)
        }
    }
}

extension Color {
    static let ink = Color(red: 0.039, green: 0.047, blue: 0.055)
    static let panel = Color(red: 0.086, green: 0.098, blue: 0.114)
    static let line = Color(red: 0.13, green: 0.15, blue: 0.18)
    static let volt = Color(red: 0.784, green: 0.945, blue: 0.208)
    static let fog = Color(red: 0.867, green: 0.890, blue: 0.910)
    static let steel = Color(red: 0.49, green: 0.53, blue: 0.58)
    static let good = Color(red: 0.24, green: 0.86, blue: 0.52)
    static let infoBlue = Color(red: 0.36, green: 0.66, blue: 1.0)
    static let warnAmber = Color(red: 1.0, green: 0.69, blue: 0.13)

    static func forStatus(_ s: String) -> Color {
        switch s { case "warn": return .warnAmber; case "info": return .infoBlue; default: return .good }
    }
}

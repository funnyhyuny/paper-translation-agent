import Foundation
import SwiftUI

enum Paths {
    static let home = FileManager.default.homeDirectoryForCurrentUser
    static let root = home.appendingPathComponent("Documents/ILOVEYELIN2")
    static let input = root.appendingPathComponent("input")
    static let output = root.appendingPathComponent("output")
    static let finished = input.appendingPathComponent("완료")
    static let rejected = input.appendingPathComponent("실패")
    static let cancelled = input.appendingPathComponent("취소")

    static let support = home.appendingPathComponent("Library/Application Support/ILOVEYELIN2")
    static let work = support.appendingPathComponent("work")
    static let python = support.appendingPathComponent("venv/bin/python")
    static let setupLog = support.appendingPathComponent("setup.log")
    static let modelCache = home.appendingPathComponent("Library/Caches/datalab")

    static var engine: URL { Bundle.main.resourceURL!.appendingPathComponent("engine") }

    /// Finder에서 실행한 앱은 셸 PATH를 받지 못하므로 직접 구성한다.
    static var environment: [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = [
            support.appendingPathComponent("bin").path,
            support.appendingPathComponent("venv/bin").path,
            home.appendingPathComponent(".local/bin").path,
            "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
        ].joined(separator: ":")
        env["PYTHONUNBUFFERED"] = "1"
        return env
    }

    static func prepareFolders() {
        for url in [input, output, finished, rejected, cancelled, work] {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        }
    }

    static func uniqueURL(for name: String, in folder: URL) -> URL {
        let base = (name as NSString).deletingPathExtension
        let ext = (name as NSString).pathExtension
        var url = folder.appendingPathComponent(name)
        var n = 2
        while FileManager.default.fileExists(atPath: url.path) {
            url = folder.appendingPathComponent("\(base) \(n).\(ext)")
            n += 1
        }
        return url
    }
}

/// 실행 파일의 stdout을 JSON 한 줄씩 메인 스레드로 전달한다.
final class EventProcess {
    private let process = Process()
    private var buffer = Data()

    init(executable: URL, arguments: [String]) {
        process.executableURL = executable
        process.arguments = arguments
        process.environment = Paths.environment
    }

    func start(onEvent: @escaping ([String: Any]) -> Void, onExit: @escaping (Int32) -> Void) {
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let self else { return }
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self.buffer.append(data)
            while let newline = self.buffer.firstIndex(of: 0x0A) {
                let line = self.buffer[self.buffer.startIndex..<newline]
                self.buffer.removeSubrange(self.buffer.startIndex...newline)
                if let object = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any] {
                    DispatchQueue.main.async { onEvent(object) }
                }
            }
        }
        process.terminationHandler = { finished in
            pipe.fileHandleForReading.readabilityHandler = nil
            let code = finished.terminationStatus
            // 마지막 이벤트가 먼저 처리되도록 메인 큐 뒤에 붙인다.
            DispatchQueue.main.async { onExit(code) }
        }
        do {
            try process.run()
        } catch {
            DispatchQueue.main.async { onExit(-1) }
        }
    }

    func stop() {
        if process.isRunning { process.terminate() }
    }
}

enum Theme {
    static let paper = Color(red: 0.965, green: 0.941, blue: 0.894)
    static let sheet = Color(red: 1.0, green: 0.992, blue: 0.973)
    static let ink = Color(red: 0.173, green: 0.149, blue: 0.125)
    static let muted = Color(red: 0.42, green: 0.37, blue: 0.31)
    static let line = Color(red: 0.878, green: 0.835, blue: 0.761)
    static let shadow = Color(red: 0.902, green: 0.863, blue: 0.788)
    static let accent = Color(red: 0.612, green: 0.239, blue: 0.180)

    static func serif(_ size: CGFloat) -> Font { .custom("AppleMyungjo", size: size) }
}

struct PrimaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(Theme.sheet)
            .padding(.horizontal, 16).padding(.vertical, 9)
            .background(Theme.accent.opacity(configuration.isPressed ? 0.8 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 3))
    }
}

struct SecondaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(Theme.ink)
            .padding(.horizontal, 16).padding(.vertical, 8)
            .background(Theme.line.opacity(configuration.isPressed ? 0.5 : 0))
            .overlay(RoundedRectangle(cornerRadius: 3).stroke(Theme.ink, lineWidth: 1))
    }
}

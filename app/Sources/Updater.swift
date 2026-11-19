import CryptoKit
import Foundation

/// GitHub Releases에 올린 version.json 형식.
struct UpdateInfo: Decodable {
    let version: String
    let build: Int
    let url: URL
    let sha256: String
    let notes: String?
}

enum Updater {
    enum Failure: LocalizedError {
        case notWritable, download, checksum, invalid

        var errorDescription: String? {
            switch self {
            case .notWritable: return "앱을 응용 프로그램 폴더로 옮긴 뒤 다시 업데이트해 주세요."
            case .download: return "새 버전을 내려받지 못했어요. 인터넷 연결을 확인해 주세요."
            case .checksum, .invalid: return "내려받은 파일이 올바르지 않아요. 잠시 뒤 다시 시도해 주세요."
            }
        }
    }

    static let feed = URL(string: ProcessInfo.processInfo.environment["ILY_UPDATE_FEED"]
        ?? "https://github.com/funnyhyuny/paper-translation-agent/releases/latest/download/version.json")!

    static var currentBuild: Int { Int(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "") ?? 0 }
    static var currentVersion: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "" }

    /// 지금보다 새 버전이 있으면 돌려준다. 오프라인이거나 릴리스가 없으면 nil.
    static func check(feed: URL = feed) async -> UpdateInfo? {
        let request = URLRequest(url: feed, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        guard let (data, _) = try? await URLSession.shared.data(for: request),
              let info = try? JSONDecoder().decode(UpdateInfo.self, from: data),
              info.build > currentBuild else { return nil }
        return info
    }

    /// 새 앱을 내려받아 검증하고 옆에 준비해 둔 뒤, 이 앱이 끝나면 교체하는 스크립트를 띄운다.
    /// 호출한 쪽은 성공하면 앱을 종료해야 한다.
    static func install(_ info: UpdateInfo, relaunch: Bool = true) async throws {
        let fm = FileManager.default
        let bundle = Bundle.main.bundleURL
        let parent = bundle.deletingLastPathComponent()
        guard !bundle.path.contains("/AppTranslocation/"), fm.isWritableFile(atPath: parent.path) else {
            throw Failure.notWritable
        }

        guard let (zip, _) = try? await URLSession.shared.download(from: info.url),
              let data = try? Data(contentsOf: zip) else { throw Failure.download }
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard digest == info.sha256.lowercased() else { throw Failure.checksum }

        let stage = fm.temporaryDirectory.appendingPathComponent("ILOVEYELIN2-update-\(UUID().uuidString)")
        defer { try? fm.removeItem(at: stage) }
        guard run("/usr/bin/ditto", ["-x", "-k", zip.path, stage.path]) == 0 else { throw Failure.invalid }
        let downloaded = stage.appendingPathComponent("ILOVEYELIN2.app")
        guard run("/usr/bin/codesign", ["--verify", "--deep", downloaded.path]) == 0 else { throw Failure.invalid }

        // 같은 폴더에 먼저 복사해 두면 교체는 이름 바꾸기만으로 끝난다.
        let staged = parent.appendingPathComponent(".ILOVEYELIN2-update.app")
        try? fm.removeItem(at: staged)
        guard run("/usr/bin/ditto", [downloaded.path, staged.path]) == 0 else { throw Failure.invalid }

        let pid = ProcessInfo.processInfo.processIdentifier
        let script = """
        while kill -0 \(pid) 2>/dev/null; do sleep 0.3; done
        if mv "$1" "$1.old"; then
          if mv "$2" "$1"; then rm -rf "$1.old"; else mv "$1.old" "$1"; fi
        fi
        \(relaunch ? "/usr/bin/open \"$1\"" : "")
        """
        let swap = Process()
        swap.executableURL = URL(fileURLWithPath: "/bin/bash")
        swap.arguments = ["-c", script, "swap", bundle.path, staged.path]
        try swap.run()
    }

    @discardableResult
    private static func run(_ tool: String, _ arguments: [String]) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: tool)
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return -1 }
        process.waitUntilExit()
        return process.terminationStatus
    }
}

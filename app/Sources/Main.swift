import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    var onQuit: (() -> Void)?
    func applicationWillTerminate(_ notification: Notification) { onQuit?() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

struct ILOVEYELIN2App: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .onAppear {
                    delegate.onQuit = { MainActor.assumeIsolated { model.quit() } }
                    model.launch()
                }
        }
        .windowResizability(.contentSize)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}

@main
enum Launcher {
    static func main() {
        let args = CommandLine.arguments
        if args.count == 3, args[1] == "--update-test", let feed = URL(string: args[2]) {
            runUpdateTest(feed: feed)
            return
        }
        if args.count == 4, args[1] == "--render" {
            MainActor.assumeIsolated { renderPreview(state: args[2], to: args[3]) }
            return
        }
        ILOVEYELIN2App.main()
    }

    /// 화면 없이 업데이트 확인과 교체를 실행해 자동 업데이트를 점검한다.
    private static func runUpdateTest(feed: URL) {
        let done = DispatchSemaphore(value: 0)
        Task.detached {
            if let info = await Updater.check(feed: feed) {
                do {
                    try await Updater.install(info, relaunch: false)
                    print("installed \(info.version) build \(info.build)")
                } catch {
                    print("failed: \(error.localizedDescription)")
                }
            } else {
                print("up to date")
            }
            done.signal()
        }
        done.wait()
    }

    /// 화면을 PNG로 그려 디자인을 점검한다.
    @MainActor
    private static func renderPreview(state: String, to path: String) {
        _ = NSApplication.shared
        let model = AppModel()
        model.history = [
            HistoryItem(url: URL(fileURLWithPath: "/x/ELC071_U1-2_KR.pdf"), date: Date()),
            HistoryItem(url: URL(fileURLWithPath: "/x/Syllabus_Fall_KR.pdf"), date: Date(timeIntervalSinceNow: -86400 * 30)),
        ]
        model.currentName = "BIA580.pdf"
        model.stageLabel = "본문을 번역하는 중"
        model.stageDetail = "5/7 섹션"
        model.fraction = 0.62
        let pdf = URL(fileURLWithPath: "/x/BIA580_KR.pdf")
        switch state {
        case "setup":
            model.steps[0].status = .done
            model.steps[1].status = .done
            model.steps[2].status = .running
            model.modelMegabytes = 1229
        case "setup-failed": model.setupFailed = true
        case "login": model.phase = .login
        case "idle": model.phase = .idle
        case "idle-update":
            model.phase = .idle
            model.update = UpdateInfo(version: "1.2", build: 3, url: URL(fileURLWithPath: "/x"), sha256: "",
                                      notes: "작업 화면에 남은 시간을 보여줘요")
        case "working":
            model.phase = .working
            model.currentStep = 3
            model.startedAt = Date(timeIntervalSinceNow: -252)
            model.lastEventAt = Date(timeIntervalSinceNow: -12)
            model.waitingCount = 1
            model.etaSeconds = 200
            model.etaAt = Date(timeIntervalSinceNow: -12)
            model.activities = [
                "전문 용어 16개를 정리했어요", "번역할 부분을 7개로 나눴어요",
                "'3 Lab 1: one-sample right-tailed' 번역을 마쳤어요", "'4 Lab 2: one-sample left-tailed' 번역을 시작했어요",
            ].enumerated().map { ActivityItem(time: Date(timeIntervalSinceNow: Double($0.offset - 4) * 40), text: $0.element) }
        case "finished":
            model.phase = .finished(FinishedJob(name: "BIA580", pdf: pdf, sourcePages: 6, pages: 7, minutes: 12, warnings: []))
        case "finished-warn":
            model.phase = .finished(FinishedJob(name: "BIA580", pdf: pdf, sourcePages: 6, pages: 7, minutes: 12,
                                                warnings: ["\"2 Methods\" 부분은 번역 분량이나 형식이 원문과 달라 확인이 필요해요."]))
        case "stopped":
            model.phase = .stopped(StoppedJob(name: "BIA580", code: "rate_limit", message: "Claude 사용량 한도에 닿았어요.",
                                              progress: "5/7 섹션까지 저장했어요", log: pdf))
        default:
            model.phase = .stopped(StoppedJob(name: "scan", code: "scanned", message: "스캔본 PDF는 지원하지 않아요.",
                                              progress: "논문을 읽는 중", log: nil))
        }
        let renderer = ImageRenderer(content: RootView(model: model))
        renderer.scale = 2
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return }
        try? png.write(to: URL(fileURLWithPath: path))
    }
}

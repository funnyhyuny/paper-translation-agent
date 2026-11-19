import AppKit
import Foundation
import UserNotifications

struct SetupStep: Identifiable {
    enum Status { case waiting, running, done }
    let id: String
    let title: String
    var status: Status = .waiting
}

struct FinishedJob {
    let name: String
    let pdf: URL
    let sourcePages: Int?
    let pages: Int?
    let minutes: Int
    let warnings: [String]
}

struct StoppedJob {
    let name: String
    let code: String
    let message: String
    let progress: String
    let log: URL?

    var canResume: Bool { code != "scanned" }
    var title: String { canResume ? "잠시 쉬어 갈게요" : "이 파일은 번역할 수 없어요" }
    var guide: String {
        switch code {
        case "rate_limit": return "한도가 풀리면 \"이어서 번역\"을 눌러 주세요. 번역한 부분은 그대로 남아 있어요."
        case "network": return "연결되면 \"이어서 번역\"을 눌러 주세요. 번역한 부분은 그대로 남아 있어요."
        case "scanned": return "글자를 선택할 수 있는 PDF로 다시 받아 주세요. 파일은 input › 실패 폴더로 옮겼어요."
        default: return "\"이어서 번역\"을 눌러 다시 시도해 주세요. 계속되면 오류 기록을 저장해 전달해 주세요."
        }
    }
}

struct ActivityItem: Identifiable {
    let id = UUID()
    let time: Date
    let text: String
}

struct HistoryItem: Identifiable {
    let url: URL
    let date: Date
    var id: URL { url }
    var name: String {
        let stem = url.deletingPathExtension().lastPathComponent
        return stem.hasSuffix("_KR") ? String(stem.dropLast(3)) : stem
    }
}

@MainActor
final class AppModel: ObservableObject {
    enum Phase {
        case setup, login, idle, working
        case finished(FinishedJob)
        case stopped(StoppedJob)
    }

    @Published var phase: Phase = .setup
    @Published var steps = AppModel.initialSteps
    @Published var modelMegabytes = 0
    @Published var setupFailed = false
    @Published var loginRunning = false
    @Published var loginURL: URL?
    @Published var currentName = ""
    @Published var stageLabel = "준비하는 중"
    @Published var stageDetail = ""
    @Published var fraction = 0.0
    @Published var waitingCount = 0
    @Published var history: [HistoryItem] = []
    @Published var hint = ""
    @Published var currentStep = 0
    @Published var activities: [ActivityItem] = []
    @Published var startedAt = Date()
    @Published var lastEventAt = Date()
    @Published var cancelling = false
    @Published var update: UpdateInfo?
    @Published var updating = false
    @Published var updateError = ""
    @Published var etaSeconds: Double?
    @Published var etaAt = Date()

    static let workSteps = ["PDF 읽기", "용어 정리", "번역할 부분 나누기", "본문 번역", "번역 검토", "PDF 만들기"]
    private static let stepOfStage = [
        "parse": 0, "glossary": 1, "split": 2, "clean": 2, "translate": 3, "validate": 4, "merge": 4, "build": 5,
    ]

    private var job: EventProcess?
    private var setupProcess: EventProcess?
    private var loginProcess: Process?
    private var loginInput: Pipe?
    private var scanTimer: Timer?
    private var updateTimer: Timer?
    private var lastSizes: [URL: Int] = [:]
    private var currentFile: URL?
    private var currentLog: URL?
    private var outcome: [String: Any]?
    private var activity: NSObjectProtocol?

    static let initialSteps = [
        SetupStep(id: "tools", title: "번역 도구 준비"),
        SetupStep(id: "python", title: "실행 환경 내려받기"),
        SetupStep(id: "models", title: "PDF 읽기 모델 내려받기"),
        SetupStep(id: "typst", title: "수식 조판 도구 준비"),
        SetupStep(id: "claude", title: "Claude 설치"),
    ]

    var isBusy: Bool {
        if case .working = phase { return true }
        return false
    }

    func launch() {
        Paths.prepareFolders()
        refreshHistory()
        runSetup()
    }

    // MARK: 첫 실행 준비

    func runSetup() {
        phase = .setup
        setupFailed = false
        steps = Self.initialSteps
        let script = Paths.engine.appendingPathComponent("setup.sh")
        let process = EventProcess(executable: URL(fileURLWithPath: "/bin/bash"), arguments: [script.path])
        setupProcess = process
        var finished = false
        process.start(onEvent: { [weak self] event in
            guard let self else { return }
            switch event["event"] as? String {
            case "step":
                guard let id = event["id"] as? String, let index = self.steps.firstIndex(where: { $0.id == id }) else { return }
                self.steps[index].status = event["status"] as? String == "done" ? .done : .running
            case "progress":
                self.modelMegabytes = event["mb"] as? Int ?? self.modelMegabytes
            case "finished":
                finished = true
            default:
                break
            }
        }, onExit: { [weak self] _ in
            guard let self else { return }
            self.setupProcess = nil
            if finished {
                self.checkLogin()
            } else {
                self.setupFailed = true
            }
        })
    }

    func saveSetupLog() { saveLog(Paths.setupLog) }

    // MARK: Claude 로그인

    private func claudeURL() -> URL? {
        let paths = (Paths.environment["PATH"] ?? "").split(separator: ":")
        return paths.map { URL(fileURLWithPath: String($0)).appendingPathComponent("claude") }
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    private func checkLogin() {
        guard let claude = claudeURL() else {
            setupFailed = true
            return
        }
        DispatchQueue.global().async {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = claude
            process.arguments = ["auth", "status"]
            process.environment = Paths.environment
            process.standardOutput = pipe
            process.standardError = FileHandle.nullDevice
            try? process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let status = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let loggedIn = status?["loggedIn"] as? Bool ?? false
            DispatchQueue.main.async {
                if loggedIn {
                    self.becomeReady()
                } else {
                    self.phase = .login
                }
            }
        }
    }

    func login() {
        guard let claude = claudeURL() else { return }
        loginRunning = true
        loginURL = nil
        let process = Process()
        let output = Pipe()
        let input = Pipe()
        process.executableURL = claude
        process.arguments = ["auth", "login", "--claudeai"]
        process.environment = Paths.environment
        process.standardOutput = output
        process.standardError = output
        process.standardInput = input
        loginProcess = process
        loginInput = input
        var text = ""
        output.fileHandleForReading.readabilityHandler = { handle in
            text += String(decoding: handle.availableData, as: UTF8.self)
            // 주소가 나뉘어 도착할 수 있으므로 줄바꿈까지 받은 뒤 읽는다.
            guard let match = text.range(of: #"https://\S+(?=\s)"#, options: .regularExpression),
                  let url = URL(string: String(text[match])) else { return }
            DispatchQueue.main.async { self.loginURL = url }
        }
        process.terminationHandler = { _ in
            output.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async {
                self.loginRunning = false
                self.loginProcess = nil
                self.loginInput = nil
                self.checkLogin()
            }
        }
        do {
            try process.run()
        } catch {
            loginRunning = false
        }
    }

    func submitLoginCode(_ code: String) {
        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        loginInput?.fileHandleForWriting.write(Data((trimmed + "\n").utf8))
    }

    private func becomeReady() {
        if case .stopped = phase { return }
        phase = .idle
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        checkForUpdate()
        updateTimer?.invalidate()
        updateTimer = Timer.scheduledTimer(withTimeInterval: 6 * 3600, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.checkForUpdate() }
        }
        scanTimer?.invalidate()
        scanTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.scanInput() }
        }
        scanInput()
    }

    // MARK: input 감시

    private func pendingFiles() -> [URL] {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: Paths.input, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey], options: [.skipsHiddenFiles]
        )) ?? []
        return urls.filter { $0.pathExtension.lowercased() == "pdf" }.sorted {
            let a = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let b = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return a < b
        }
    }

    func scanInput() {
        let files = pendingFiles()
        waitingCount = files.filter { $0 != currentFile }.count
        switch phase {
        case .idle, .finished: break
        default: return
        }
        // 복사가 끝나지 않은 파일을 읽지 않도록 크기가 그대로인 파일만 시작한다.
        var sizes: [URL: Int] = [:]
        for file in files {
            sizes[file] = (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        }
        let ready = files.first { sizes[$0] != 0 && sizes[$0] == lastSizes[$0] }
        lastSizes = sizes
        if let ready { start(ready) }
    }

    func add(urls: [URL]) {
        var skipped = false
        for url in urls {
            guard url.pathExtension.lowercased() == "pdf" else {
                skipped = true
                continue
            }
            try? FileManager.default.copyItem(at: url, to: Paths.uniqueURL(for: url.lastPathComponent, in: Paths.input))
        }
        hint = skipped ? "PDF 파일만 번역할 수 있어요" : ""
        scanInput()
    }

    func choosePDF() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = true
        if panel.runModal() == .OK { add(urls: panel.urls) }
    }

    // MARK: 번역 실행

    private func start(_ file: URL) {
        currentFile = file
        currentLog = nil
        outcome = nil
        currentName = file.lastPathComponent
        stageLabel = "준비하는 중"
        stageDetail = ""
        fraction = 0
        currentStep = 0
        activities = []
        cancelling = false
        etaSeconds = nil
        startedAt = Date()
        lastEventAt = Date()
        phase = .working
        activity = ProcessInfo.processInfo.beginActivity(
            options: [.idleSystemSleepDisabled, .userInitiated], reason: "논문 번역"
        )
        let process = EventProcess(executable: Paths.python, arguments: [
            Paths.engine.appendingPathComponent("pipeline.py").path, file.path,
            "--work-root", Paths.work.path, "--output-dir", Paths.output.path,
        ])
        job = process
        process.start(onEvent: { [weak self] in self?.handle($0) }, onExit: { [weak self] in self?.jobExited($0) })
    }

    private func handle(_ event: [String: Any]) {
        lastEventAt = Date()
        switch event["event"] as? String {
        case "eta":
            etaSeconds = (event["seconds"] as? NSNumber)?.doubleValue
            etaAt = Date()
        case "activity":
            guard let text = event["text"] as? String else { return }
            activities.append(ActivityItem(time: Date(), text: text))
            if activities.count > 30 { activities.removeFirst(activities.count - 30) }
        case "job":
            currentLog = (event["log"] as? String).map { URL(fileURLWithPath: $0) }
        case "stage":
            stageLabel = event["label"] as? String ?? stageLabel
            if let stage = event["stage"] as? String, let step = Self.stepOfStage[stage] { currentStep = step }
            fraction = event["fraction"] as? Double ?? fraction
            if let done = event["done"] as? Int, let total = event["total"] as? Int, total > 0 {
                stageDetail = "\(done)/\(total) 섹션"
            } else {
                stageDetail = ""
            }
        case "done", "error":
            outcome = event
        default:
            break
        }
    }

    private func jobExited(_ code: Int32) {
        job = nil
        if let activity { ProcessInfo.processInfo.endActivity(activity) }
        activity = nil
        guard let file = currentFile else { return }
        currentFile = nil
        let name = file.deletingPathExtension().lastPathComponent
        if cancelling && outcome?["event"] as? String != "done" {
            cancelling = false
            try? FileManager.default.moveItem(at: file, to: Paths.uniqueURL(for: file.lastPathComponent, in: Paths.cancelled))
            hint = "번역을 취소했어요. 같은 파일을 다시 넣으면 하던 곳부터 이어서 번역해요."
            phase = .idle
            lastSizes = [:]
            return
        }
        cancelling = false
        if outcome?["event"] as? String == "done", let path = outcome?["pdf"] as? String {
            let minutes = max(1, Int(Date().timeIntervalSince(startedAt) / 60 + 0.5))
            try? FileManager.default.moveItem(at: file, to: Paths.uniqueURL(for: file.lastPathComponent, in: Paths.finished))
            phase = .finished(FinishedJob(
                name: name, pdf: URL(fileURLWithPath: path),
                sourcePages: outcome?["source_pages"] as? Int, pages: outcome?["pages"] as? Int,
                minutes: minutes, warnings: outcome?["warnings"] as? [String] ?? []
            ))
            notify(title: "번역을 마쳤어요", body: "\(name) 번역본이 output 폴더에 있어요.")
            refreshHistory()
            return
        }
        let errorCode = outcome?["code"] as? String ?? "failed"
        let message = outcome?["message"] as? String ?? "번역이 중간에 멈췄어요."
        if errorCode == "auth" {
            phase = .login
            return
        }
        if errorCode == "scanned" {
            try? FileManager.default.moveItem(at: file, to: Paths.uniqueURL(for: file.lastPathComponent, in: Paths.rejected))
        }
        let progress = stageDetail.isEmpty ? stageLabel : "\(stageDetail)까지 저장했어요"
        phase = .stopped(StoppedJob(name: name, code: errorCode, message: message, progress: progress, log: currentLog))
        notify(title: "번역이 멈췄어요", body: message)
    }

    // MARK: 자동 업데이트

    func checkForUpdate() {
        Task {
            let info = await Updater.check()
            await MainActor.run { self.update = info }
        }
    }

    /// 번역 중이 아닐 때만 새 버전으로 교체하고 다시 켠다.
    func installUpdate() {
        guard let update, !isBusy, !updating else { return }
        updating = true
        updateError = ""
        Task {
            do {
                try await Updater.install(update)
                await MainActor.run { NSApp.terminate(nil) }
            } catch {
                await MainActor.run {
                    self.updating = false
                    self.updateError = error.localizedDescription
                }
            }
        }
    }

    /// 마지막 예상치에서 그 뒤로 흐른 시간을 빼서 남은 시간을 문장으로 만든다.
    func remainingText(at now: Date) -> String {
        guard let etaSeconds else { return "남은 시간 계산 중" }
        let left = etaSeconds - now.timeIntervalSince(etaAt)
        if left <= 0 { return "곧 끝나요" }
        if left < 60 { return "1분 이내 남음" }
        return "약 \(Int((left / 60).rounded(.up)))분 남음"
    }

    /// 진행 중인 번역을 멈추고 원본을 input/취소 폴더로 옮긴다.
    func cancel() {
        guard isBusy, !cancelling else { return }
        cancelling = true
        activities.append(ActivityItem(time: Date(), text: "번역을 취소하는 중이에요"))
        job?.stop()
    }

    func resume() {
        phase = .idle
        lastSizes = [:]
        scanInput()
    }

    func quit() {
        job?.stop()
        setupProcess?.stop()
        loginProcess?.terminate()
    }

    // MARK: 결과

    func refreshHistory() {
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: Paths.output, includingPropertiesForKeys: [.contentModificationDateKey], options: [.skipsHiddenFiles]
        )) ?? []
        history = urls.filter { $0.pathExtension.lowercased() == "pdf" }.map {
            HistoryItem(url: $0, date: (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast)
        }.sorted { $0.date > $1.date }
    }

    func open(_ url: URL) { NSWorkspace.shared.open(url) }
    func reveal(_ url: URL) { NSWorkspace.shared.activateFileViewerSelecting([url]) }

    func saveLog(_ log: URL?) {
        guard let log else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "ILOVEYELIN2-오류기록.txt"
        if panel.runModal() == .OK, let target = panel.url {
            try? FileManager.default.removeItem(at: target)
            try? FileManager.default.copyItem(at: log, to: target)
        }
    }

    private func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }
}

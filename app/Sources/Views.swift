import SwiftUI
import UniformTypeIdentifiers

struct RootView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Group {
            switch model.phase {
            case .setup: SetupView(model: model)
            case .login: LoginView(model: model)
            case .idle: IdleView(model: model)
            case .working: WorkingView(model: model)
            case .finished(let job): FinishedView(model: model, job: job)
            case .stopped(let job): StoppedView(model: model, job: job)
            }
        }
        .padding(.horizontal, 34).padding(.top, 30).padding(.bottom, 26)
        .frame(width: 480, height: 640, alignment: .topLeading)
        .background(Theme.paper)
        .foregroundColor(Theme.ink)
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            for provider in providers {
                _ = provider.loadObject(ofClass: URL.self) { url, _ in
                    guard let url else { return }
                    DispatchQueue.main.async { model.add(urls: [url]) }
                }
            }
            return true
        }
    }
}

struct Title: View {
    let text: String
    var body: some View {
        Text(text).font(Theme.serif(30)).fontWeight(.bold).lineSpacing(6).fixedSize(horizontal: false, vertical: true)
    }
}

struct Note: View {
    let text: String
    var body: some View {
        Text(text).font(.system(size: 13)).foregroundColor(Theme.muted).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
    }
}

struct Sheet<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        content
            .frame(maxWidth: .infinity)
            .padding(20)
            .background(Theme.sheet)
            .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
            .background(Rectangle().fill(Theme.shadow).offset(x: 4, y: 4))
    }
}

struct DropSheet: View {
    @ObservedObject var model: AppModel
    var body: some View {
        Button(action: model.choosePDF) {
            Sheet {
                VStack(spacing: 7) {
                    Text("여기에 PDF를 끌어다 놓기").font(Theme.serif(17))
                    Text("또는 문서 › ILOVEYELIN2 › input 폴더에 넣기").font(.system(size: 12)).foregroundColor(Theme.muted)
                }
                .padding(.vertical, 18)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct ProgressLine: View {
    let fraction: Double
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle().fill(Theme.line)
                Rectangle().fill(Theme.accent).frame(width: geo.size.width * min(max(fraction, 0), 1))
            }
        }
        .frame(height: 4)
    }
}

struct SetupView: View {
    @ObservedObject var model: AppModel
    private let modelTotal = 3300.0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Title(text: model.setupFailed ? "준비를 마치지 못했어요" : "번역 책상을\n준비하고 있어요")
            Note(text: model.setupFailed
                 ? "인터넷 연결과 저장 공간을 확인한 뒤 다시 시도해 주세요."
                 : "처음 한 번만 필요해요. 인터넷과 전원을 연결해 두세요.")
                .padding(.top, 10)
            VStack(spacing: 0) {
                ForEach(model.steps) { step in
                    HStack(spacing: 12) {
                        Text(mark(step.status)).font(.system(size: 14, weight: .bold)).foregroundColor(Theme.accent).frame(width: 16)
                        Text(label(step)).font(.system(size: 14))
                            .foregroundColor(step.status == .waiting ? Theme.muted : Theme.ink)
                        Spacer()
                    }
                    .padding(.vertical, 12)
                    Rectangle().fill(Theme.line).frame(height: 1)
                }
            }
            .padding(.top, 20)
            Spacer()
            if model.setupFailed {
                HStack(spacing: 10) {
                    Button("다시 시도", action: model.runSetup).buttonStyle(PrimaryButton())
                    Button("오류 기록 저장", action: model.saveSetupLog).buttonStyle(SecondaryButton())
                }
            } else {
                ProgressLine(fraction: overall)
                Note(text: "창을 닫아도 다음에 이어서 준비해요").padding(.top, 9)
            }
        }
    }

    private var overall: Double {
        let done = Double(model.steps.filter { $0.status == .done }.count)
        return done / Double(max(model.steps.count, 1))
    }

    private func mark(_ status: SetupStep.Status) -> String {
        switch status {
        case .done: return "✓"
        case .running: return "…"
        case .waiting: return ""
        }
    }

    private func label(_ step: SetupStep) -> String {
        guard step.id == "models", step.status == .running, model.modelMegabytes > 0 else { return step.title }
        let got = Double(model.modelMegabytes) / 1024
        return String(format: "%@ · %.1fGB / %.1fGB", step.title, got, modelTotal / 1024)
    }
}

struct LoginView: View {
    @ObservedObject var model: AppModel
    @State private var code = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Title(text: "마지막으로\nClaude에 로그인해요")
            Note(text: "번역은 내 Claude 계정으로 진행해요. 버튼을 누르면 브라우저가 열리고, 로그인 후 이 창으로 돌아오면 돼요.")
                .padding(.top, 10)
            Button(model.loginRunning ? "브라우저에서 로그인하는 중…" : "Claude 로그인", action: model.login)
                .buttonStyle(PrimaryButton())
                .disabled(model.loginRunning)
                .padding(.top, 24)
            if let url = model.loginURL {
                Button("브라우저가 열리지 않으면 여기를 눌러 주세요") { model.open(url) }
                    .buttonStyle(.plain).font(.system(size: 12)).foregroundColor(Theme.accent).padding(.top, 12)
                Note(text: "브라우저에 코드가 표시되면 아래에 붙여 넣어 주세요.").padding(.top, 18)
                HStack(spacing: 10) {
                    TextField("로그인 코드", text: $code).textFieldStyle(.roundedBorder)
                    Button("확인") { model.submitLoginCode(code) }.buttonStyle(CompactButton())
                }
                .padding(.top, 8)
            }
            Spacer()
        }
    }
}

struct IdleView: View {
    @ObservedObject var model: AppModel
    private static let dateFormat: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "ko_KR")
        f.dateFormat = "M월 d일 완성"
        return f
    }()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Title(text: "오늘 읽을 논문을\n놓아 주세요")
            DropSheet(model: model).padding(.top, 22)
            if !model.hint.isEmpty {
                Text(model.hint).font(.system(size: 12)).foregroundColor(Theme.accent).padding(.top, 12)
            }
            Spacer(minLength: 16)
            if model.history.isEmpty {
                Note(text: "완성한 번역본은 여기에 모여요")
            } else {
                Rectangle().fill(Theme.ink).frame(height: 1)
                ForEach(model.history.prefix(3)) { item in
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.name).font(Theme.serif(15)).fontWeight(.bold).lineLimit(1)
                            Text(Self.dateFormat.string(from: item.date)).font(.system(size: 11)).foregroundColor(Theme.muted)
                        }
                        Spacer()
                        Button("PDF 열기") { model.open(item.url) }.buttonStyle(CompactButton())
                    }
                    .padding(.vertical, 10)
                    Rectangle().fill(Theme.line).frame(height: 1)
                }
            }
            UpdateBanner(model: model)
            HStack {
                Button("output 폴더 열기") { model.open(Paths.output) }
                    .buttonStyle(.plain).font(.system(size: 12)).foregroundColor(Theme.muted)
                Spacer()
                Text("버전 \(Updater.currentVersion)").font(.system(size: 11)).foregroundColor(Theme.muted)
            }
            .padding(.top, 12)
        }
    }
}

/// 새 버전이 있을 때 대기 화면 아래에 나타난다.
struct UpdateBanner: View {
    @ObservedObject var model: AppModel

    var body: some View {
        if let update = model.update {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("새 버전 \(update.version)이 나왔어요").font(.system(size: 13, weight: .semibold))
                        if let notes = update.notes, !notes.isEmpty {
                            Text(notes).font(.system(size: 11)).foregroundColor(Theme.muted).lineLimit(2)
                        }
                    }
                    Spacer()
                    Button(model.updating ? "업데이트 중…" : "업데이트") { model.installUpdate() }
                        .buttonStyle(CompactButton())
                        .disabled(model.updating)
                }
                if !model.updateError.isEmpty {
                    Text(model.updateError).font(.system(size: 11)).foregroundColor(Theme.accent)
                }
            }
            .padding(12)
            .background(Theme.sheet)
            .overlay(Rectangle().fill(Theme.accent).frame(width: 3), alignment: .leading)
            .padding(.top, 14)
        }
    }
}

struct CompactButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: 12, weight: .semibold)).foregroundColor(Theme.sheet)
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.accent.opacity(configuration.isPressed ? 0.8 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 3))
    }
}

struct WorkingView: View {
    @ObservedObject var model: AppModel
    @State private var confirmCancel = false

    private static let clock: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f
    }()

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            VStack(alignment: .leading, spacing: 0) {
                Title(text: "논문을 번역하고 있어요")
                Sheet {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.currentName).font(Theme.serif(16)).fontWeight(.bold).lineLimit(1).truncationMode(.middle)
                        ProgressLine(fraction: model.fraction)
                        HStack {
                            Text("\(Int(model.fraction * 100))%").font(.system(size: 13, weight: .semibold)).monospacedDigit()
                            Spacer()
                            Text("경과 \(duration(context.date.timeIntervalSince(model.startedAt)))")
                                .font(.system(size: 12)).foregroundColor(Theme.muted).monospacedDigit()
                            Text("·").font(.system(size: 12)).foregroundColor(Theme.muted)
                            Text(model.remainingText(at: context.date))
                                .font(.system(size: 12, weight: .semibold)).foregroundColor(Theme.accent)
                        }
                    }
                }
                .padding(.top, 18)

                VStack(spacing: 0) {
                    ForEach(Array(AppModel.workSteps.enumerated()), id: \.offset) { index, title in
                        StepRow(title: title, index: index, current: model.currentStep,
                                detail: index == model.currentStep ? model.stageDetail : "")
                    }
                }
                .padding(.top, 16)

                Text("진행 기록").font(.system(size: 11, weight: .semibold)).foregroundColor(Theme.muted).padding(.top, 16)
                VStack(alignment: .leading, spacing: 5) {
                    if model.activities.isEmpty {
                        Text("준비하고 있어요").font(.system(size: 12)).foregroundColor(Theme.muted)
                    }
                    ForEach(model.activities.suffix(6)) { item in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(Self.clock.string(from: item.time)).font(.system(size: 11)).foregroundColor(Theme.muted).monospacedDigit()
                            Text(item.text).font(.system(size: 12)).lineLimit(1).truncationMode(.middle)
                        }
                    }
                }
                .padding(.top, 6)

                Spacer(minLength: 10)
                HStack(alignment: .center) {
                    Note(text: pulse(context.date))
                    Spacer()
                    Button(model.cancelling ? "취소하는 중…" : "번역 취소") { confirmCancel = true }
                        .buttonStyle(SecondaryButton())
                        .disabled(model.cancelling)
                }
            }
        }
        .confirmationDialog("번역을 취소할까요?", isPresented: $confirmCancel) {
            Button("번역 취소", role: .destructive) { model.cancel() }
            Button("계속 번역", role: .cancel) {}
        } message: {
            Text("원본은 input › 취소 폴더로 옮겨요. 같은 파일을 다시 넣으면 하던 곳부터 이어서 번역해요.")
        }
    }

    /// 마지막 진행 소식이 언제였는지 알려 지금도 일하는 중인지 보여준다.
    private func pulse(_ now: Date) -> String {
        let quiet = now.timeIntervalSince(model.lastEventAt)
        let waiting = model.waitingCount > 0 ? " · 다음 차례 \(model.waitingCount)개" : ""
        if quiet < 60 { return "정상 진행 중 · 마지막 소식 \(Int(quiet))초 전" + waiting }
        if quiet < 180 { return "정상 진행 중 · 마지막 소식 \(Int(quiet / 60))분 전" + waiting }
        return "이 단계가 오래 걸리고 있어요 · \(Int(quiet / 60))분째 작업 중" + waiting
    }

    private func duration(_ seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        return s >= 60 ? "\(s / 60)분 \(s % 60)초" : "\(s)초"
    }
}

struct StepRow: View {
    let title: String
    let index: Int
    let current: Int
    let detail: String

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                if index < current {
                    Text("✓").font(.system(size: 13, weight: .bold)).foregroundColor(Theme.accent)
                } else if index == current {
                    Circle().fill(Theme.accent).frame(width: 8, height: 8)
                }
            }
            .frame(width: 16)
            Text(title)
                .font(.system(size: 13, weight: index == current ? .semibold : .regular))
                .foregroundColor(index > current ? Theme.muted : Theme.ink)
            Spacer()
            Text(detail).font(.system(size: 12)).foregroundColor(Theme.accent)
        }
        .padding(.vertical, 6)
        .overlay(Rectangle().fill(Theme.line).frame(height: 1), alignment: .bottom)
    }
}

struct FinishedView: View {
    @ObservedObject var model: AppModel
    let job: FinishedJob

    private var summary: String {
        var parts = [job.name]
        if let source = job.sourcePages, let pages = job.pages { parts.append("원문 \(source)쪽 → 번역본 \(pages)쪽") }
        parts.append("\(job.minutes)분 걸림")
        return parts.joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Title(text: "번역을 마쳤어요")
            Note(text: summary).padding(.top, 10)
            Sheet {
                VStack(alignment: .leading, spacing: 6) {
                    Text(job.pdf.lastPathComponent).font(Theme.serif(17)).lineLimit(2)
                    Text("문서 › ILOVEYELIN2 › output").font(.system(size: 12)).foregroundColor(Theme.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.top, 22)
            HStack(spacing: 10) {
                Button("PDF 열기") { model.open(job.pdf) }.buttonStyle(PrimaryButton())
                Button("폴더에서 보기") { model.reveal(job.pdf) }.buttonStyle(SecondaryButton())
            }
            .padding(.top, 20)
            if !job.warnings.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    Text("확인이 필요해요").font(.system(size: 13, weight: .semibold))
                    ForEach(job.warnings.prefix(3), id: \.self) { Text($0).font(.system(size: 12)).lineSpacing(2) }
                }
                .padding(12).frame(maxWidth: .infinity, alignment: .leading).background(Theme.sheet)
                .overlay(Rectangle().fill(Theme.accent).frame(width: 3), alignment: .leading)
                .padding(.top, 20)
            }
            Spacer(minLength: 12)
            HStack {
                Note(text: "새 논문을 놓으면 바로 이어서 번역해요")
                Spacer()
                Button("처음으로") { model.resume() }.buttonStyle(.plain).font(.system(size: 12)).foregroundColor(Theme.accent)
            }
        }
    }
}

struct StoppedView: View {
    @ObservedObject var model: AppModel
    let job: StoppedJob

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Title(text: job.title)
            Note(text: "\(job.name) · \(job.progress)").padding(.top, 10)
            VStack(alignment: .leading, spacing: 6) {
                Text(job.message).font(.system(size: 14, weight: .semibold))
                Text(job.guide).font(.system(size: 13)).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            }
            .padding(15).frame(maxWidth: .infinity, alignment: .leading).background(Theme.sheet)
            .overlay(Rectangle().fill(Theme.accent).frame(width: 3), alignment: .leading)
            .padding(.top, 22)
            HStack(spacing: 10) {
                Button(job.canResume ? "이어서 번역" : "확인", action: model.resume).buttonStyle(PrimaryButton())
                if job.log != nil {
                    Button("오류 기록 저장") { model.saveLog(job.log) }.buttonStyle(SecondaryButton())
                }
            }
            .padding(.top, 20)
            Spacer()
        }
    }
}

#!/usr/bin/env python3
"""ILOVEYELIN2 자동 번역 실행기.

CLAUDE.md의 워크플로우를 게이트 없이 실행한다. 진행 상황은 stdout에 JSON 한 줄씩
보고하고, 단계 완료는 progress.log에 남겨 재실행 시 이어서 진행한다.

Usage:
    pipeline.py <input.pdf> --work-root DIR --output-dir DIR
"""

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
SKILLS = Path(os.environ.get("ILY_SKILLS", ENGINE / "skills"))
AGENT_MD = Path(os.environ.get("ILY_AGENT", ENGINE / "agents/translator/AGENT.md"))

MODEL = os.environ.get("ILY_MODEL", "sonnet")
WORKERS = 3
MAX_SECTION_WORDS = 4000
GLOSSARY_SOURCE_CHARS = 150_000
CLAUDE_TIMEOUT = 600
DONE = "<!-- DONE -->"
# 한국어는 영어보다 글자 수가 훨씬 적어 정상 번역도 0.4~0.6이 나온다. 이보다 낮으면 누락으로 본다.
MIN_KOREAN_LENGTH_RATIO = 0.35

# 재시도해도 소용없어 즉시 멈추는 오류
RATE_RE = re.compile(r"usage limit|rate.?limit|limit reached|hit your .*limit|session limit|\b429\b", re.I)
AUTH_RE = re.compile(r"not logged in|/login|invalid api key|authentication|\b401\b|oauth", re.I)
NET_RE = re.compile(r"enotfound|econn|etimedout|network|connection error|unable to connect", re.I)

# 예상 시간 계산 기준 (M5 Pro 실측: 10쪽 PDF 읽기 약 100초, 번역 초당 약 70단어). M1에서는 더 느릴 수 있다.
PARSE_BASE_SEC, PARSE_SEC_PER_PAGE = 12, 9
GLOSSARY_SEC, TAIL_SEC = 10, 15
TRANSLATE_WORDS_PER_SEC, CLEAN_WORDS_PER_SEC = 70, 90

HARD_ERROR_RE = re.compile(r"missing|image count|DONE", re.I)
MATH_COUNT_RE = re.compile(r"math count mismatch: src=(\d+) kr=(\d+)")
# 이 개수를 넘게 수식이 달라지면 내용이 빠진 것으로 보고 멈춘다. 그 이하는 표기 차이로 보고 경고만 남긴다.
MAX_MATH_DIFF = 2
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
META_LINE_RE = re.compile(r"^\s*<!--\s*meta:.*?-->\s*\n?")
ADDENDUM_RE = re.compile(r"<!--\s*ADDENDUM:\s*(\[.*?\])\s*-->", re.S)
MATH_SPAN_RE = re.compile(r"\$\$.+?\$\$|\$[^\n$]+?\$", re.S)
BROKEN_MATH_RE = re.compile(r"[∑∫≤≥≠∈∉√∞±÷⇒≈σμλπθαβγδ∂∇�]")
GLUED_RE = re.compile(r"\b[a-z]+[A-Z][a-z]{2,}\b")

TEXT_MODE = f"""

---

## 이 실행의 입출력 (위 1·2절의 파일 입출력보다 우선)

파일 도구는 없다. 사용자 메시지로 글로서리와 섹션 원문을 받고, 번역 결과만 응답으로 출력한다.

- 번역된 마크다운 전문만 출력한다. 설명 문장과 코드 펜스로 감싸기는 금지한다.
- 첫 줄의 `<!-- meta: ... -->` 주석은 출력하지 않는다.
- 글로서리에 없는 신규 전문용어가 있으면 마지막 줄 바로 앞에
  `<!-- ADDENDUM: [{{"en": "...", "ko": "...", "note": "..."}}] -->`를 한 줄로 쓴다.
- 응답의 마지막 줄은 정확히 `{DONE}` 이다.
"""

CLEAN_SYSTEM = f"""너는 PDF에서 추출한 영문 마크다운의 파싱 오류만 고치는 복구기다.

- 붙어 버린 단어를 띄어 쓴다. (예: InAnalytics → In Analytics)
- 평문으로 깨진 수식을 LaTeX `$...$`, `$$...$$`로 복원한다.
- 내용을 추가·삭제·요약·번역하지 않는다. 이미지 참조, 인용, 표 구조, 헤딩은 그대로 둔다.
- 첫 줄의 `<!-- meta: ... -->` 주석은 출력하지 않는다.
- 고친 마크다운 전문만 출력하고, 마지막 줄은 정확히 `{DONE}` 이다.
"""

GLOSSARY_SYSTEM = """너는 영문 학술 문서에서 번역 용어집과 서지 정보를 뽑는다.
아래 형식의 JSON 객체 하나만 출력한다. 설명과 코드 펜스는 쓰지 않는다.

{"title_ko": "한국어 제목", "title_en": "원문 제목", "authors": "저자", "source": "출처와 연도",
 "glossary": [{"en": "attention mechanism", "ko": "어텐션 메커니즘", "note": "첫 등장 시 병기"}]}

- glossary에는 고유명사, 일관된 표기가 필요한 기술용어, 저자가 정의한 개념을 5개 이상 담는다.
- CNN 같은 약어는 ko에 원문을 그대로 쓴다.
- 모르는 서지 정보는 빈 문자열로 둔다.
"""


def eta(seconds: float) -> None:
    """앱에 남은 예상 시간을 알린다."""
    emit("eta", seconds=max(5, int(seconds)))


def word_count(paths) -> int:
    return sum(len(re.findall(r"\w+", strip_meta(p.read_text(encoding="utf-8"))[1])) for p in paths)


def activity(text: str) -> None:
    """앱의 진행 기록에 한 줄을 남긴다."""
    emit("activity", text=text)


def section_title(path: Path) -> str:
    title = parse_meta(path.read_text(encoding="utf-8")).get("title") or ""
    title = re.sub(r"<[^>]+>|[*#_`]", "", title).strip()
    if title in ("", "(untitled)"):
        return "본문"
    if title == "Preamble":
        return "첫머리"
    return title if len(title) <= 30 else title[:29] + "…"


class StopPipeline(Exception):
    """사용자에게 보여줄 오류로 파이프라인을 멈춘다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ClaudeRetryable(Exception):
    pass


def emit(event: str, **fields) -> None:
    with _emit_lock:
        print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


_emit_lock = threading.Lock()
_children: set = set()
_children_lock = threading.Lock()
_cancelled = threading.Event()


def run(cmd, *, input_text=None, timeout=None, cwd=None, env=None):
    """자식을 별도 프로세스 그룹으로 실행해 종료 신호 때 함께 정리한다."""
    proc = subprocess.Popen(
        [str(c) for c in cmd],
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    with _children_lock:
        _children.add(proc)
    try:
        out, err = proc.communicate(input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return subprocess.CompletedProcess(cmd, 124, out, (err or "") + "\ntimed out")
    finally:
        with _children_lock:
            _children.discard(proc)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def on_terminate(_signum, _frame):
    _cancelled.set()
    with _children_lock:
        for proc in list(_children):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    os._exit(143)


def watch_parent() -> None:
    """앱이 강제 종료되면 번역 프로세스가 남지 않도록 함께 끝낸다."""
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            on_terminate(None, None)


def natural_key(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def strip_meta(text: str) -> tuple[str, str]:
    """(메타 줄, 나머지 본문)을 돌려준다."""
    m = META_LINE_RE.match(text)
    if not m:
        return "", text
    return m.group(0).strip(), text[m.end():]


def parse_meta(text: str) -> dict:
    meta_line, _ = strip_meta(text)
    m = re.search(r"\{.*\}", meta_line)
    return json.loads(m.group(0)) if m else {}


def strip_fence(text: str) -> str:
    t = text.strip()
    m = re.fullmatch(r"```[a-zA-Z]*\n(.*)\n```", t, re.S)
    return m.group(1).strip() if m else t


def parse_marked_reply(reply: str) -> tuple[str, list]:
    """DONE으로 끝나는 응답에서 (본문, addendum)을 분리한다."""
    text = strip_fence(reply)
    lines = text.rstrip().splitlines()
    if not lines or lines[-1].strip() != DONE:
        raise ClaudeRetryable("응답이 완료 표시 없이 끝남")
    body = "\n".join(lines[:-1])
    addendum = []
    m = ADDENDUM_RE.search(body)
    if m:
        try:
            addendum = json.loads(m.group(1))
        except json.JSONDecodeError:
            addendum = []
        body = ADDENDUM_RE.sub("", body)
    _, body = strip_meta(body)
    return body.strip(), addendum


def looks_broken(text: str) -> bool:
    plain = MATH_SPAN_RE.sub("", text)
    return bool(BROKEN_MATH_RE.search(plain)) or len(GLUED_RE.findall(plain)) >= 2


def real_errors(errors: list) -> list:
    """검증 오류 중 한국어의 정상적인 글자 수 압축으로 생긴 길이 오류를 뺀다."""
    kept = []
    for error in errors:
        m = re.match(r"length ratio ([\d.]+) out of", error)
        if m and MIN_KOREAN_LENGTH_RATIO <= float(m.group(1)) < 1:
            continue
        kept.append(error)
    return kept


def is_hard_error(error: str) -> bool:
    """멈춰야 하는 검증 오류인지 판단한다."""
    m = MATH_COUNT_RE.search(error)
    if m:
        return abs(int(m.group(1)) - int(m.group(2))) > MAX_MATH_DIFF
    return bool(HARD_ERROR_RE.search(error))


def join_cell(cell: str) -> str:
    """단어마다 끊긴 표 셀을 잇는다. 몇 줄뿐인 의도된 줄바꿈은 그대로 둔다."""
    parts = [p.strip() for p in re.split(r"<br\s*/?>", cell)]
    words = sum(len(p.split()) for p in parts)
    if len(parts) >= 6 and words / len(parts) <= 1.5:
        return " " + " ".join(p for p in parts if p) + " "
    return cell


def strip_anchors(text: str) -> str:
    """marker가 남긴 빈 페이지 앵커를 지운다. Typst는 이를 라벨 문법으로 읽어 조판에 실패한다."""
    return re.sub(r"<span\s+id=\"[^\"]*\"\s*>\s*</span>", "", text)


def normalize_tables(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("|"):
            line = "|".join(join_cell(cell) for cell in line.split("|"))
            # 표 패딩은 토큰을 낭비하고 번역 길이 검증을 왜곡한다.
            line = re.sub(r"-{4,}", "---", re.sub(r" {2,}", " ", line))
        lines.append(line)
    return "\n".join(lines) + "\n"


def split_paragraphs(body: str, max_words: int) -> list[str]:
    """수식·코드 블록을 끊지 않고 문단 경계에서 나눈다."""
    chunks, buf, words = [], [], 0
    for para in re.split(r"\n{2,}", body):
        buf.append(para)
        words += len(re.findall(r"\w+", para))
        joined = "\n\n".join(buf)
        in_block = joined.count("$$") % 2 or joined.count("```") % 2
        if words >= max_words and not in_block:
            chunks.append(joined)
            buf, words = [], 0
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def subdivide_sections(sections_dir: Path, max_words: int = MAX_SECTION_WORDS) -> None:
    """응답 길이 한도를 넘지 않도록 긴 섹션을 다시 나눈다."""
    for path in sorted(sections_dir.glob("sec_*.md")):
        text = path.read_text(encoding="utf-8")
        meta_line, body = strip_meta(text)
        if parse_meta(text).get("translate") is False:
            continue
        if len(re.findall(r"\w+", body)) <= max_words:
            continue
        parts = split_paragraphs(body.strip(), max_words)
        if len(parts) < 2:
            continue
        for i, part in enumerate(parts):
            target = path.with_name(f"{path.stem}_p{i:02d}.md")
            target.write_text(f"{meta_line}\n{part}\n", encoding="utf-8")
        path.unlink()


def clean_typst_string(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("\\", "").replace('"', "'").strip()


def merge_glossary(glossary: list, addenda: list) -> tuple[list, list]:
    """같은 영어 용어는 먼저 정해진 표기를 유지한다. (병합 결과, 충돌 목록)"""
    merged = list(glossary)
    known = {str(g.get("en", "")).lower(): g.get("ko") for g in glossary}
    conflicts = []
    for item in addenda:
        key = str(item.get("en", "")).lower()
        if not key:
            continue
        if key not in known:
            known[key] = item.get("ko")
            merged.append(item)
        elif known[key] != item.get("ko"):
            conflicts.append(item)
    return merged, conflicts


def merge_sections(sections_dir: Path, kr_dir: Path) -> str:
    """번역 섹션을 순서대로 합친다. 번역 제외 섹션은 원문을 참고문헌으로 붙인다."""
    parts = []
    for src in sorted(sections_dir.glob("sec_*.md"), key=lambda p: natural_key(p.name)):
        text = src.read_text(encoding="utf-8")
        if parse_meta(text).get("translate") is False:
            _, body = strip_meta(text)
            body = re.sub(r"^#+ .*$", "## 참고문헌", body.strip(), count=1, flags=re.M)
            parts.append(body)
            continue
        kr = (kr_dir / f"{src.stem}_kr.md").read_text(encoding="utf-8")
        _, body = strip_meta(kr)
        parts.append(body.replace(DONE, "").strip())
    merged = "\n\n".join(parts) + "\n"
    # 원문은 이미지를 파일명으로만 참조하므로 images/ 폴더로 연결한다.
    return re.sub(r"(!\[[^\]]*\]\()(?!images/|https?:|/)", r"\1images/", merged)


class Claude:
    def __init__(self, work: Path, log):
        self.work = work
        self.log = log
        self.bin = shutil.which("claude") or "claude"

    def _once(self, system: str, prompt: str) -> str:
        cmd = [
            self.bin, "-p", "--model", MODEL, "--tools", "", "--system-prompt", system,
            "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
            "--no-session-persistence", "--output-format", "json",
        ]
        env = {**os.environ, "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000"}
        res = run(cmd, input_text=prompt, timeout=CLAUDE_TIMEOUT, cwd=self.work, env=env)
        try:
            data = json.loads(res.stdout)
        except (json.JSONDecodeError, TypeError):
            data = {}
        text = str(data.get("result") or "")
        failed = res.returncode != 0 or data.get("is_error") or not data
        if failed:
            detail = f"{text}\n{res.stdout or ''}\n{res.stderr or ''}"
            self.log(f"[claude] 실패 rc={res.returncode}: {detail[:800]}")
            if RATE_RE.search(detail):
                raise StopPipeline("rate_limit", "Claude 사용량 한도에 닿았어요.")
            if AUTH_RE.search(detail):
                raise StopPipeline("auth", "Claude 로그인이 필요해요.")
            if NET_RE.search(detail):
                raise StopPipeline("network", "인터넷 연결을 확인해 주세요.")
            raise ClaudeRetryable(detail[:300])
        if data.get("stop_reason") == "max_tokens":
            raise ClaudeRetryable("응답이 길이 한도에서 잘림")
        return text

    def ask(self, system: str, prompt: str, parse):
        """응답을 parse로 해석한다. 호출이나 해석이 실패하면 1회 재시도한다."""
        last = None
        for _ in range(2):
            try:
                return parse(self._once(system, prompt))
            except ClaudeRetryable as exc:
                last = exc
                self.log(f"[claude] 재시도: {exc}")
                activity("Claude 응답이 고르지 않아 다시 요청했어요")
        raise StopPipeline("failed", f"Claude 응답을 처리하지 못했어요. ({last})")


class Job:
    def __init__(self, pdf: Path, work_root: Path, output_dir: Path):
        self.pdf = pdf
        self.output_dir = output_dir
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:8]
        self.stem = unicodedata.normalize("NFC", pdf.stem)
        self.work = work_root / f"{self.stem}-{digest}"
        self.work.mkdir(parents=True, exist_ok=True)
        self.sections = self.work / "sections"
        self.sections_kr = self.work / "sections_kr"
        self.sections_raw = self.work / "sections_raw"
        self.progress = self.work / "progress.log"
        self.logfile = self.work / "pipeline.log"
        self.warnings_file = self.work / "warnings.json"
        self.claude = Claude(self.work, self.log)
        emit("job", log=str(self.logfile), work=str(self.work))

    # 공통
    def log(self, message: str) -> None:
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        with self.logfile.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")

    def is_done(self, step: str) -> bool:
        if not self.progress.exists():
            return False
        return any(ln.startswith(f"{step}: Done") for ln in self.progress.read_text(encoding="utf-8").splitlines())

    def mark_done(self, step: str, note: str = "") -> None:
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        with self.progress.open("a", encoding="utf-8") as f:
            f.write(f"{step}: Done {stamp} {note}\n".rstrip() + "\n")

    def warnings(self) -> list:
        if self.warnings_file.exists():
            return json.loads(self.warnings_file.read_text(encoding="utf-8"))
        return []

    def warn(self, message: str) -> None:
        items = self.warnings()
        if message not in items:
            items.append(message)
            self.warnings_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def stage(self, stage: str, label: str, fraction: float, done=None, total=None) -> None:
        emit("stage", stage=stage, label=label, fraction=round(fraction, 3), done=done, total=total)

    def script(self, relative: str, *args, env=None):
        res = run([sys.executable, SKILLS / relative, *args], cwd=self.work, env=env)
        self.log(f"[{relative}] rc={res.returncode}\n{res.stdout}\n{res.stderr}")
        return res

    def parallel(self, items, work, on_done) -> None:
        with cf.ThreadPoolExecutor(WORKERS) as pool:
            futures = [pool.submit(work, item) for item in items]
            try:
                for count, future in enumerate(cf.as_completed(futures), 1):
                    future.result()
                    on_done(count)
            except BaseException:
                for future in futures:
                    future.cancel()
                raise

    # 단계
    def parse(self) -> None:
        self.stage("parse", "논문을 읽는 중", 0.03)
        pdf = self.work / "source.pdf"
        shutil.copyfile(self.pdf, pdf)
        pages = self.page_count(pdf)
        activity(f"PDF에서 글자와 그림을 읽고 있어요{f' · {pages}쪽' if pages else ''}")
        p = pages or 10
        eta(PARSE_BASE_SEC + PARSE_SEC_PER_PAGE * p + GLOSSARY_SEC + p * 400 * (1 / TRANSLATE_WORDS_PER_SEC + 0.5 / CLEAN_WORDS_PER_SEC) + TAIL_SEC)
        env = {**os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1"}
        res = self.script("pdf-parser/scripts/parse_pdf.py", pdf, self.work, env={**env, "TORCH_DEVICE": "mps"})
        if res.returncode not in (0, 4):
            self.log("MPS 변환 실패, CPU로 재시도")
            self.stage("parse", "논문을 다시 읽는 중", 0.05)
            res = self.script("pdf-parser/scripts/parse_pdf.py", pdf, self.work, env={**env, "TORCH_DEVICE": "cpu"})
        if res.returncode == 4:
            raise StopPipeline("scanned", "스캔본 PDF는 지원하지 않아요.")
        if res.returncode != 0:
            raise StopPipeline("failed", "PDF를 읽지 못했어요. 메모리가 부족하거나 손상된 파일일 수 있어요.")
        source = self.work / "source.md"
        source.write_text(normalize_tables(strip_anchors(source.read_text(encoding="utf-8"))), encoding="utf-8")
        images = len([p for p in (self.work / "images").glob("*") if not p.name.startswith("_")])
        activity(f"PDF를 다 읽었어요 · 그림 {images}개")
        self.mark_done("step_1_parse", str(self.work / "source.md"))

    def glossary(self) -> None:
        self.stage("glossary", "용어를 정리하는 중", 0.27)
        source = (self.work / "source.md").read_text(encoding="utf-8")[:GLOSSARY_SOURCE_CHARS]
        words = len(re.findall(r"\w+", source))
        eta(GLOSSARY_SEC + words * (1 / TRANSLATE_WORDS_PER_SEC + 0.5 / CLEAN_WORDS_PER_SEC) + TAIL_SEC)

        def parse(reply: str) -> dict:
            text = strip_fence(reply)
            try:
                data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            except ValueError as exc:
                raise ClaudeRetryable(f"용어집 JSON 오류: {exc}")
            if not isinstance(data.get("glossary"), list):
                raise ClaudeRetryable("용어집 항목 없음")
            return data

        data = self.claude.ask(GLOSSARY_SYSTEM, source, parse)
        glossary = data.pop("glossary")
        if len(glossary) < 5:
            self.warn(f"용어집이 {len(glossary)}개뿐이에요. 용어 표기를 확인해 주세요.")
        (self.work / "glossary.json").write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.work / "meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        activity(f"전문 용어 {len(glossary)}개를 정리했어요")
        self.mark_done("step_3_glossary", f"{len(glossary)}개 항목")

    def split(self) -> None:
        self.stage("split", "섹션을 나누는 중", 0.31)
        shutil.rmtree(self.sections, ignore_errors=True)
        res = self.script("section-splitter/scripts/split.py", self.work / "source.md", self.sections)
        if res.returncode != 0:
            raise StopPipeline("failed", "논문을 섹션으로 나누지 못했어요.")
        subdivide_sections(self.sections)
        activity(f"번역할 부분을 {len(self.translatable())}개로 나눴어요")
        self.mark_done("step_4_split", f"{len(list(self.sections.glob('sec_*.md')))}개 섹션")

    def translatable(self) -> list:
        paths = sorted(self.sections.glob("sec_*.md"), key=lambda p: natural_key(p.name))
        return [p for p in paths if parse_meta(p.read_text(encoding="utf-8")).get("translate") is not False]

    def clean(self) -> None:
        self.sections_raw.mkdir(exist_ok=True)
        todo = [
            p for p in self.translatable()
            if not (self.sections_raw / p.name).exists() and looks_broken(p.read_text(encoding="utf-8"))
        ]
        self.stage("clean", "깨진 수식을 복원하는 중", 0.33, 0, len(todo))
        translate_sec = word_count(self.translatable()) / TRANSLATE_WORDS_PER_SEC + TAIL_SEC
        eta(word_count(todo) / CLEAN_WORDS_PER_SEC + translate_sec)
        started = time.time()

        def cleaned(n: int) -> None:
            self.stage("clean", "깨진 수식을 복원하는 중", 0.33 + 0.07 * n / len(todo), n, len(todo))
            eta((time.time() - started) / n * (len(todo) - n) + translate_sec)

        def work(path: Path) -> None:
            text = path.read_text(encoding="utf-8")
            meta_line, body = strip_meta(text)
            fixed, _ = self.claude.ask(CLEAN_SYSTEM, body, parse_marked_reply)
            same_images = len(IMAGE_RE.findall(fixed)) == len(IMAGE_RE.findall(body))
            ratio = len(fixed) / max(len(body), 1)
            shutil.copyfile(path, self.sections_raw / path.name)
            if same_images and 0.8 <= ratio <= 1.3:
                path.write_text(f"{meta_line}\n{fixed}\n", encoding="utf-8")
                activity(f"'{section_title(path)}' 수식을 복원했어요")
            else:
                self.log(f"[clean] {path.name} 복구 결과 폐기 (이미지 일치={same_images}, 길이비={ratio:.2f})")

        self.parallel(todo, work, cleaned)
        self.mark_done("step_4a_clean", f"{len(todo)}개 섹션 복구 시도")

    def translate_one(self, path: Path, feedback: str = "") -> None:
        text = path.read_text(encoding="utf-8")
        meta_line, body = strip_meta(text)
        glossary = (self.work / "glossary.json").read_text(encoding="utf-8")
        system = AGENT_MD.read_text(encoding="utf-8") + TEXT_MODE
        prompt = f"# 글로서리\n{glossary}\n\n# 번역할 섹션\n{body}"
        title = section_title(path)
        activity(f"'{title}' 다시 번역을 시작했어요" if feedback else f"'{title}' 번역을 시작했어요")
        if feedback:
            prompt += f"\n\n# 이전 번역에서 발견된 문제 (반드시 해결)\n{feedback}"
        translated, addendum = self.claude.ask(system, prompt, parse_marked_reply)
        (self.sections_kr / f"{path.stem}_kr.md").write_text(f"{meta_line}\n{translated}\n{DONE}\n", encoding="utf-8")
        if addendum:
            (self.sections_kr / f"{path.stem}_addendum.json").write_text(
                json.dumps(addendum, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        activity(f"'{title}' 번역을 마쳤어요")

    def translate(self) -> None:
        self.sections_kr.mkdir(exist_ok=True)
        sections = self.translatable()
        total = len(sections)

        def finished(path: Path) -> bool:
            kr = self.sections_kr / f"{path.stem}_kr.md"
            return kr.exists() and kr.read_text(encoding="utf-8").rstrip().endswith(DONE)

        todo = [p for p in sections if not finished(p)]
        base = total - len(todo)

        started = time.time()

        def report(done: int) -> None:
            self.stage("translate", "본문을 번역하는 중", 0.40 + 0.46 * done / max(total, 1), done, total)
            finished_now = done - base
            if finished_now > 0:
                eta((time.time() - started) / finished_now * (len(todo) - finished_now) + TAIL_SEC)
            else:
                eta(word_count(todo) / TRANSLATE_WORDS_PER_SEC + TAIL_SEC)

        report(base)
        self.parallel(todo, self.translate_one, lambda n: report(base + n))
        self.mark_done("step_5_translate", f"{total}/{total} 섹션")

    def run_validator(self) -> dict:
        """{섹션: 오류 목록} 형태로 실제 문제만 돌려준다."""
        res = self.script("translation-validator/scripts/validate.py", self.sections, self.sections_kr)
        if res.returncode == 2:
            raise StopPipeline("failed", "번역 결과를 검증하지 못했어요.")
        report = json.loads(res.stdout)
        failures = {stem: real_errors(report[stem]["errors"]) for stem in report["summary"]["failed"]}
        return {stem: errors for stem, errors in failures.items() if errors}

    def validate(self) -> None:
        self.stage("validate", "번역을 검토하는 중", 0.87)
        eta(TAIL_SEC)
        failures = self.run_validator()
        if failures:
            self.log(f"[validate] 재번역 대상: {failures}")
            self.stage("validate", "어색한 섹션을 다시 번역하는 중", 0.88)
            redo_words = word_count([self.sections / f"{stem}.md" for stem in failures])
            eta(redo_words / TRANSLATE_WORDS_PER_SEC * WORKERS / max(1, min(WORKERS, len(failures))) + TAIL_SEC)

            def redo(stem: str) -> None:
                self.translate_one(self.sections / f"{stem}.md", "\n".join(failures[stem]))

            self.parallel(list(failures), redo, lambda _n: None)
            failures = self.run_validator()
        hard = []
        for stem, errors in failures.items():
            if any(is_hard_error(e) for e in errors):
                hard.append(f"{stem}: {'; '.join(errors)}")
            elif any(MATH_COUNT_RE.search(e) for e in errors):
                self.warn(f"'{section_title(self.sections / f'{stem}.md')}' 부분의 수식 표기 일부가 원문과 달라 확인이 필요해요.")
            else:
                self.warn(f"'{section_title(self.sections / f'{stem}.md')}' 부분은 번역 분량이나 형식이 원문과 달라 확인이 필요해요.")
        if hard:
            self.log(f"[validate] 복구 실패: {hard}")
            raise StopPipeline("verify", "번역본에서 그림이나 수식 여러 개가 빠졌어요.")
        count = len(self.warnings())
        activity(f"번역 검토를 마쳤어요 · 확인이 필요한 곳 {count}개" if count else "번역 검토를 마쳤어요 · 문제없어요")
        self.mark_done("step_6_validate", f"경고 {count}건")

    def merge(self) -> None:
        self.stage("merge", "번역을 하나로 합치는 중", 0.91)
        glossary = json.loads((self.work / "glossary.json").read_text(encoding="utf-8"))
        addenda = []
        for path in sorted(self.sections_kr.glob("*_addendum.json"), key=lambda p: natural_key(p.name)):
            addenda.extend(json.loads(path.read_text(encoding="utf-8")))
        final, conflicts = merge_glossary(glossary, addenda)
        (self.work / "glossary_final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        if conflicts:
            self.log(f"[merge] 용어 충돌, 먼저 정해진 표기 유지: {conflicts}")
        (self.work / "merged_kr.md").write_text(merge_sections(self.sections, self.sections_kr), encoding="utf-8")
        self.mark_done("step_6_merge", str(self.work / "merged_kr.md"))

    def build(self) -> None:
        self.stage("build", "PDF를 만드는 중", 0.94)
        eta(10)
        meta = json.loads((self.work / "meta.json").read_text(encoding="utf-8"))
        merged = self.work / "merged_kr.md"
        merged.write_text(strip_anchors(merged.read_text(encoding="utf-8")), encoding="utf-8")
        args = [
            self.work / "merged_kr.md", self.work / "body.typ",
            "--meta-title", clean_typst_string(meta.get("title_ko")) or self.stem,
            "--meta-orig-title", clean_typst_string(meta.get("title_en")),
            "--meta-authors", clean_typst_string(meta.get("authors")),
            "--meta-source", clean_typst_string(meta.get("source")),
        ]
        for extra in (["--mitex"], []):
            if self.script("typst-builder/scripts/md_to_typst.py", *args, *extra).returncode != 0:
                continue
            res = self.script("typst-builder/scripts/build_pdf.py", self.work / "body.typ", self.work / "final.pdf")
            if res.returncode == 0:
                pages = self.page_count(self.work / "final.pdf")
                activity(f"번역본 PDF를 만들었어요{f' · {pages}쪽' if pages else ''}")
                self.mark_done("step_7_build", str(self.work / "final.pdf"))
                return
        raise StopPipeline("build", "PDF를 조판하지 못했어요.")

    @staticmethod
    def page_count(pdf: Path):
        try:
            import fitz
            with fitz.open(pdf) as doc:
                return doc.page_count
        except Exception:
            return None

    def page_counts(self) -> tuple:
        try:
            import fitz
        except ImportError:
            return None, None
        with fitz.open(self.work / "source.pdf") as src, fitz.open(self.work / "final.pdf") as out:
            return src.page_count, out.page_count

    def deliver(self) -> None:
        result_file = self.work / "result.json"
        if result_file.exists():
            result = json.loads(result_file.read_text(encoding="utf-8"))
            if Path(result["pdf"]).exists():
                emit("done", **result)
                return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / f"{self.stem}_KR.pdf"
        n = 2
        while target.exists():
            target = self.output_dir / f"{self.stem}_KR {n}.pdf"
            n += 1
        shutil.copyfile(self.work / "final.pdf", target)
        source_pages, pages = self.page_counts()
        if source_pages and pages and not 0.7 <= pages / source_pages <= 1.3:
            self.log(f"[build] 쪽수 차이: 원문 {source_pages}쪽, 번역본 {pages}쪽 (표지·목차 포함)")
        result = {"pdf": str(target), "source_pages": source_pages, "pages": pages, "warnings": self.warnings()}
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        emit("done", **result)

    def run(self) -> None:
        steps = [
            ("step_1_parse", self.parse),
            ("step_3_glossary", self.glossary),
            ("step_4_split", self.split),
            ("step_4a_clean", self.clean),
            ("step_5_translate", self.translate),
            ("step_6_validate", self.validate),
            ("step_6_merge", self.merge),
            ("step_7_build", self.build),
        ]
        if any(self.is_done(name) for name, _ in steps):
            activity("전에 하던 곳부터 이어서 번역해요")
        for name, step in steps:
            if not self.is_done(name):
                step()
        self.deliver()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, on_terminate)
    threading.Thread(target=watch_parent, daemon=True).start()
    job = None
    try:
        job = Job(args.pdf, args.work_root, args.output_dir)
        job.run()
        return 0
    except StopPipeline as exc:
        emit("error", code=exc.code, message=exc.message)
        return 1
    except Exception as exc:  # 앱이 이유를 표시할 수 있도록 모두 보고한다
        if job:
            job.log(f"[오류] {exc!r}")
        emit("error", code="failed", message=f"예상하지 못한 문제가 생겼어요. ({type(exc).__name__})")
        return 1


if __name__ == "__main__":
    sys.exit(main())

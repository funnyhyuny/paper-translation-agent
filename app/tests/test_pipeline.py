"""가짜 claude와 가짜 marker로 pipeline.py 전체 흐름을 검증한다.

실행: python3 -m unittest discover -s app/tests
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
PIPELINE = APP / "engine/pipeline.py"

spec = importlib.util.spec_from_file_location("pipeline", PIPELINE)
pipeline = importlib.util.module_from_spec(spec)
sys.modules["pipeline"] = pipeline
os.environ.setdefault("ILY_SKILLS", str(ROOT / ".claude/skills"))
spec.loader.exec_module(pipeline)

SOURCE_MD = """# <span id="page-0-0"></span>Paper Title

Abstract text about bond pricing. This abstract is long enough to look like a real text page, so the scanned document check does not reject the test fixture on its character count alone.

## 1 Introduction

Intro with $x^2$ and a figure.

![](_page_0_Figure_1.jpeg)

## 2 Methods

We measured duration.

## References

[1] Smith, 2020.
"""

FAKE_MARKER = """#!/usr/bin/env python3
import base64, os, sys
from pathlib import Path
pdf = Path(sys.argv[1]); out = Path(sys.argv[sys.argv.index('--output_dir') + 1]) / pdf.stem
out.mkdir(parents=True, exist_ok=True)
(out / (pdf.stem + '.md')).write_text(os.environ['FAKE_SOURCE'], encoding='utf-8')
(out / '_page_0_Figure_1.jpeg').write_bytes(base64.b64decode(os.environ['FAKE_JPEG']))
"""

# 사용자 메시지에서 원문을 읽어 규칙대로 "번역"한다. FAKE_MODE로 오류를 흉내 낸다.
FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path
args = sys.argv[1:]
prompt = sys.stdin.read()
system = args[args.index('--system-prompt') + 1]
state = Path(os.environ['FAKE_STATE'])
calls = int(state.read_text()) if state.exists() else 0
state.write_text(str(calls + 1))
with open(os.environ['FAKE_ARGS'], 'a') as f:
    f.write(json.dumps(args) + '\n')
mode = os.environ.get('FAKE_MODE', '')
limit_after = int(os.environ.get('FAKE_LIMIT_AFTER', '-1'))

def reply(text, **extra):
    print(json.dumps({'result': text, 'is_error': False, 'stop_reason': 'end_turn', **extra}))
    sys.exit(0)

if mode == 'slow' and '번역할 섹션' in prompt:
    with open(os.environ['FAKE_PIDS'], 'a') as f:
        f.write(f"{os.getpid()}\n")
    import time
    time.sleep(60)
if calls == limit_after:
    print(json.dumps({'result': "You've hit your usage limit", 'is_error': True}))
    sys.exit(1)
if mode == 'auth':
    print(json.dumps({'result': 'Not logged in · Please run /login', 'is_error': True}))
    sys.exit(1)
if 'glossary' in system and '서지' in system:
    reply(json.dumps({'title_ko': '채권 "가격" 연구', 'title_en': 'Bond', 'authors': 'Kim', 'source': '2026',
        'glossary': [{'en': f'term{i}', 'ko': f'용어{i}', 'note': ''} for i in range(6)]}, ensure_ascii=False))
if '복구기' in system:
    reply(prompt.replace('InAnalytics', 'In Analytics') + '\n<!-- DONE -->')
section = prompt.split('# 번역할 섹션\n', 1)[1].split('\n\n# 이전 번역', 1)[0]
if mode == 'drop_image' and '# 이전 번역' in prompt or mode == 'drop_image':
    section = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', section)
if mode == 'no_done_once' and calls < 3:
    reply('번역 일부')
if mode == 'short' and '# 이전 번역' not in prompt or mode == 'short_always':
    section = section[:3]
tail = '<!-- ADDENDUM: [{"en": "duration", "ko": "듀레이션", "note": ""}] -->\n' if 'duration' in section else ''
reply('번역: ' + section + '\n' + tail + '<!-- DONE -->')
"""

JPEG_SCRIPT = (
    "import base64,io,sys\nfrom PIL import Image\nb=io.BytesIO()\n"
    "Image.new('RGB',(300,120),'red').save(b,'JPEG')\nprint(base64.b64encode(b.getvalue()).decode())"
)


def write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class Env:
    def __init__(self, source=SOURCE_MD, **fake):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        write_exec(self.bin / "marker_single", FAKE_MARKER)
        write_exec(self.bin / "claude", FAKE_CLAUDE)
        self.pdf = self.tmp / "논문 (1).pdf"
        self.make_pdf()
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_SOURCE": source,
            "FAKE_JPEG": subprocess.run([PYTHON, "-c", JPEG_SCRIPT], capture_output=True, text=True, check=True).stdout.strip(),
            "FAKE_STATE": str(self.tmp / "calls"),
            "FAKE_ARGS": str(self.tmp / "args"),
            "FAKE_PIDS": str(self.tmp / "pids"),
            "ILY_SKILLS": str(ROOT / ".claude/skills"),
            "ILY_AGENT": str(ROOT / ".claude/agents/translator/AGENT.md"),
            **fake,
        }

    def make_pdf(self):
        script = "import fitz,sys\nd=fitz.open()\nd.new_page().insert_text((72,72),'hello')\nd.save(sys.argv[1])"
        subprocess.run([PYTHON, "-c", script, str(self.pdf)], check=True)

    def run(self, **override):
        res = subprocess.run(
            [PYTHON, str(PIPELINE), str(self.pdf), "--work-root", str(self.tmp / "work"), "--output-dir", str(self.tmp / "out")],
            capture_output=True, text=True, env={**self.env, **override},
        )
        events = [json.loads(line) for line in res.stdout.splitlines() if line.strip()]
        return res, events

    def work(self) -> Path:
        return next((self.tmp / "work").iterdir())


PYTHON = os.environ.get("ILY_TEST_PYTHON", "/opt/anaconda3/bin/python")


class Units(unittest.TestCase):
    def test_natural_order_keeps_ten_after_two(self):
        names = ["sec_10.md", "sec_2_p01.md", "sec_2_p00.md", "sec_1.md"]
        self.assertEqual(sorted(names, key=pipeline.natural_key), ["sec_1.md", "sec_2_p00.md", "sec_2_p01.md", "sec_10.md"])

    def test_reply_without_done_marker_is_retryable(self):
        with self.assertRaises(pipeline.ClaudeRetryable):
            pipeline.parse_marked_reply("잘린 번역")

    def test_reply_extracts_addendum_and_fence(self):
        body, addendum = pipeline.parse_marked_reply('```markdown\n본문\n<!-- ADDENDUM: [{"en":"a","ko":"가"}] -->\n<!-- DONE -->\n```')
        self.assertEqual(body, "본문")
        self.assertEqual(addendum, [{"en": "a", "ko": "가"}])

    def test_split_never_cuts_a_math_block(self):
        body = "one two three\n\n$$\na\n\nb\n$$\n\nfour five"
        parts = pipeline.split_paragraphs(body, 2)
        self.assertTrue(all(p.count("$$") % 2 == 0 for p in parts))
        self.assertEqual("\n\n".join(parts), body)

    def test_broken_detection_ignores_valid_math(self):
        self.assertFalse(pipeline.looks_broken("Good text with $\\sigma ≤ 1$ only."))
        self.assertTrue(pipeline.looks_broken("0 ≤ p(x) ≤ 1 for all x"))

    def test_glossary_merge_keeps_first_mapping(self):
        merged, conflicts = pipeline.merge_glossary([{"en": "Bond", "ko": "채권"}], [{"en": "bond", "ko": "본드"}, {"en": "yield", "ko": "수익률"}])
        self.assertEqual([m["ko"] for m in merged], ["채권", "수익률"])
        self.assertEqual(len(conflicts), 1)

    def test_word_per_line_table_cell_is_joined(self):
        row = "| a<br>b<br>c<br>d<br>e<br>f | keep<br>this |"
        self.assertEqual(pipeline.normalize_tables(row).strip(), "| a b c d e f | keep<br>this |")

    def test_sentence_line_breaks_in_cell_are_kept(self):
        row = "| first full sentence here<br>second full sentence here |"
        self.assertEqual(pipeline.normalize_tables(row).strip(), row)

    def test_table_padding_is_removed(self):
        text = "| a      | b   |\n|--------|:---:|\n"
        self.assertEqual(pipeline.normalize_tables(text), "| a | b |\n|---|:---:|\n")

    def test_korean_compression_is_not_an_error(self):
        self.assertEqual(pipeline.real_errors(["length ratio 0.46 out of [0.6, 1.2]"]), [])

    def test_real_omission_and_overlong_output_stay_errors(self):
        errors = ["length ratio 0.20 out of [0.6, 1.2]", "length ratio 1.50 out of [0.6, 1.2]", "image count mismatch: src=1 kr=0"]
        self.assertEqual(pipeline.real_errors(errors), errors)

    def test_one_missing_inline_math_is_only_a_warning(self):
        self.assertFalse(pipeline.is_hard_error("inline math count mismatch: src=22 kr=21"))
        self.assertTrue(pipeline.is_hard_error("inline math count mismatch: src=22 kr=15"))
        self.assertTrue(pipeline.is_hard_error("image count mismatch: src=1 kr=0"))

    def test_section_title_hides_marker_anchors(self):
        import tempfile as tf
        path = Path(tf.mkdtemp()) / "sec_1.md"
        path.write_text('<!-- meta: {"title": "<span id=\\"page-3-0\\"></span>3 Lab 1"} -->\nx', encoding="utf-8")
        self.assertEqual(pipeline.section_title(path), "3 Lab 1")

    def test_page_anchors_are_removed(self):
        self.assertEqual(pipeline.strip_anchors('## <span id="page-2-0"></span>**1 Intro**'), "## **1 Intro**")

    def test_typst_string_is_safe(self):
        self.assertEqual(pipeline.clean_typst_string('a "b"\\\n c'), "a 'b' c")


class EndToEnd(unittest.TestCase):
    def test_full_run_outputs_pdf_with_isolated_claude(self):
        env = Env()
        res, events = env.run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        done = events[-1]
        self.assertEqual(done["event"], "done")
        self.assertTrue(Path(done["pdf"]).exists())
        self.assertEqual(Path(done["pdf"]).name, "논문 (1)_KR.pdf")
        merged = (env.work() / "merged_kr.md").read_text(encoding="utf-8")
        self.assertIn("](images/_page_0_Figure_1.jpeg)", merged)
        self.assertIn("## 참고문헌", merged)
        self.assertIn("[1] Smith, 2020.", merged)
        self.assertNotIn("<!-- DONE -->", merged)
        first = json.loads((env.tmp / "args").read_text().splitlines()[0])
        for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--setting-sources"):
            self.assertIn(flag, first)
        self.assertEqual(first[first.index("--tools") + 1], "")
        final = json.loads((env.work() / "glossary_final.json").read_text(encoding="utf-8"))
        self.assertIn("duration", [g["en"] for g in final])

    def test_activity_log_reports_each_section(self):
        env = Env()
        _, events = env.run()
        texts = [e["text"] for e in events if e["event"] == "activity"]
        self.assertTrue(any("PDF를 다 읽었어요" in t for t in texts), texts)
        self.assertTrue(any("'1 Introduction' 번역을 마쳤어요" in t for t in texts), texts)
        self.assertTrue(any("번역본 PDF를 만들었어요" in t for t in texts), texts)

    def test_remaining_time_is_reported_and_ends_small(self):
        env = Env()
        _, events = env.run()
        etas = [e["seconds"] for e in events if e["event"] == "eta"]
        self.assertGreaterEqual(len(etas), 4)
        self.assertGreater(etas[0], etas[-1])
        self.assertLessEqual(etas[-1], 15)

    def test_cancel_stops_pipeline_and_its_claude_calls(self):
        import signal, time
        env = Env(FAKE_MODE="slow")
        proc = subprocess.Popen(
            [PYTHON, str(PIPELINE), str(env.pdf), "--work-root", str(env.tmp / "work"), "--output-dir", str(env.tmp / "out")],
            stdout=subprocess.PIPE, text=True, env=env.env,
        )
        for line in proc.stdout:
            if "번역을 시작했어요" in line:
                break
        deadline = time.time() + 10
        while not (env.tmp / "pids").exists() and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(0.5)
        started = time.time()
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        self.assertLess(time.time() - started, 5)
        time.sleep(0.5)
        for pid in (env.tmp / "pids").read_text().split():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid), 0)

    def test_rate_limit_stops_then_resumes_without_redoing_work(self):
        env = Env(FAKE_LIMIT_AFTER="2")
        res, events = env.run()
        self.assertEqual(res.returncode, 1)
        self.assertEqual(events[-1]["code"], "rate_limit")
        self.assertEqual(list((env.tmp / "out").glob("*.pdf")) if (env.tmp / "out").exists() else [], [])
        translated = list((env.work() / "sections_kr").glob("*_kr.md"))
        self.assertTrue(translated)
        res, events = env.run(FAKE_LIMIT_AFTER="-1")
        self.assertEqual(events[-1]["event"], "done", res.stdout)
        first_translate = next(e for e in events if e.get("stage") == "translate")
        self.assertEqual(first_translate["done"], len(translated))
        self.assertNotIn("glossary", [e.get("stage") for e in events])

    def test_auth_failure_is_reported_without_retry(self):
        env = Env(FAKE_MODE="auth")
        _, events = env.run()
        self.assertEqual(events[-1]["code"], "auth")
        self.assertEqual((env.tmp / "calls").read_text(), "1")

    def test_truncated_reply_is_retried(self):
        env = Env(FAKE_MODE="no_done_once")
        res, events = env.run()
        self.assertEqual(events[-1]["event"], "done", res.stdout)

    def test_lost_image_stops_for_verification(self):
        env = Env(FAKE_MODE="drop_image")
        _, events = env.run()
        self.assertEqual(events[-1]["code"], "verify")

    def test_soft_validation_failure_finishes_with_warning(self):
        long = SOURCE_MD.replace("We measured duration.", "We measured duration. " * 40)
        long = long.replace("![](_page_0_Figure_1.jpeg)", "").replace("$x^2$", "x")
        env = Env(source=long, FAKE_MODE="short_always")
        _, events = env.run()
        self.assertEqual(events[-1]["event"], "done")
        self.assertTrue(events[-1]["warnings"])

    def test_scanned_pdf_is_rejected(self):
        env = Env(source="x")
        _, events = env.run()
        self.assertEqual(events[-1]["code"], "scanned")

    def test_rerun_of_finished_file_reports_same_pdf(self):
        env = Env()
        _, first = env.run()
        _, second = env.run()
        self.assertEqual(first[-1]["pdf"], second[-1]["pdf"])
        self.assertEqual(len(list((env.tmp / "out").glob("*.pdf"))), 1)

    def test_long_section_without_headings_is_subdivided(self):
        body = "\n\n".join(["word " * 1500] * 4)
        env = Env(source=f"## One\n\n{body}\n\n## Two\n\nend text here.\n")
        res, events = env.run()
        self.assertEqual(events[-1]["event"], "done", res.stdout)
        self.assertGreater(len(list((env.work() / "sections").glob("sec_*_p*.md"))), 1)


if __name__ == "__main__":
    unittest.main()

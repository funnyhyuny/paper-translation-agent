#!/usr/bin/env python3
"""마크다운(merged_kr.md)을 Typst 본문 소스로 변환한다.

Usage:
    python md_to_typst.py <merged.md> <body.typ> \
        --meta-title <한국어 제목> \
        --meta-orig-title <영문 제목> \
        --meta-authors <저자> \
        --meta-source <원문 출처>

출력 body.typ은 paper.typ 템플릿을 import하여 paper(...) 함수 호출 형태로 작성된다.
변환 규칙:
- # / ## / ###  → = / == / ===
- **bold** → *bold*
- *italic* → _italic_
- ![alt](path) → #figure(image("path"), caption: [alt])
- $$...$$ → $ ... $ (Typst 디스플레이 수식)
- $...$ → $...$ (Typst 인라인 수식)
- LaTeX 명령은 가능한 한 그대로 두되, Typst 환경에서 호환되지 않는 부분은 raw 블록으로 감싼다.
- 표(파이프) → #table(...) 단순 변환
"""

import argparse
import math
import os
import datetime as dt
import re
import sys
from pathlib import Path


def escape_typst_text(s: str) -> str:
    """Typst에서 의미 있는 문자(@ # _ * ` $ \\)를 이스케이프."""
    # 순서 중요: 백슬래시 먼저
    s = s.replace("\\", "\\\\")
    for ch in ["@", "#", "_", "*", "`", "$"]:
        s = s.replace(ch, "\\" + ch)
    return s


def convert_inline(text: str) -> str:
    """인라인 마크다운 → Typst.

    bold/italic, 인라인 코드, 링크, 이미지, 수식을 처리하고
    Typst 마크업 문자(#, ~, @)를 이스케이프한다.
    """
    holders: list[str] = []

    def hold(rendered: str) -> str:
        holders.append(rendered)
        return f"\x00H{len(holders) - 1}\x00"

    # marker가 남긴 HTML 잔재: <br> → 줄바꿈, <sup>x</sup> → 위첨자
    text = re.sub(r"<br\s*/?>", r"\\ ", text)
    text = re.sub(r"<sup>(.*?)</sup>", lambda m: hold(f"#super[{m.group(1)}]"), text)

    # 인라인 수식 $...$ 는 먼저 홀더로 빼서 강조·이스케이프 규칙에서 보호한다.
    # 앞에 백슬래시가 붙은 \$ (금액 표기)는 구분자가 아니므로 제외한다.
    text = re.sub(
        r"(?<!\\)\$((?:\\\$|[^$\n])+?)(?<!\\)\$",
        lambda m: hold("$" + convert_math(m.group(1)) + "$"),
        text,
    )

    # bold **x** → *x* : 이탤릭 규칙이 다시 매칭하지 않도록 플레이스홀더 경유
    text = re.sub(r"\*\*([^*\n]+?)\*\*", lambda m: hold(f"#strong[{m.group(1)}]"), text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", lambda m: hold(f"#emph[{m.group(1)}]"), text)

    # 링크 [text](url) → #link("url")[text], 오토링크 <url> → #link("url")
    text = re.sub(
        r"\[([^\]]+)\]\(((?:https?://|mailto:)[^)]+)\)",
        lambda m: hold(f'#link("{m.group(2)}")[{escape_markup(m.group(1))}]'),
        text,
    )
    text = re.sub(
        r"<((?:https?://|mailto:)[^>\s]+)>",
        lambda m: hold(f'#link("{m.group(1)}")'),
        text,
    )

    # 남은 본문의 Typst 특수문자 이스케이프.
    #   @ → 라벨 참조, # → 코드 표현식 시작, ~ → 비분리 공백
    # 으로 해석되어 이메일 주소·"ECM #1"·"10~11시간"이 사라진다.
    text = escape_markup(text)

    for i, h in enumerate(holders):
        text = text.replace(f"\x00H{i}\x00", h)

    # `#strong[x](주석)` 처럼 강조 바로 뒤에 오는 괄호/대괄호를 Typst가 함수 인자로
    # 해석하므로 이스케이프한다. 한국어 병기 표기에서 항상 발생하는 패턴이다.
    text = re.sub(
        r"(#(?:strong|emph)\[(?:[^\[\]]|\[[^\]]*\])*\])([(\[])",
        r"\1\\\2",
        text,
    )
    return text


def convert_math(m: str) -> str:
    r"""LaTeX 수식 본문 → Typst 수식 문법.

    marker가 뽑아내는 수식은 LaTeX 문법이라 Typst에서 그대로 컴파일되지 않는다.
    - `^{...}` / `_{...}` → `^(...)` / `_(...)`  (Typst에서 `{`는 코드 블록)
    - `\times`, `\approx` 등 명령어 → Typst 함수명
    - 수식 안의 달러 기호는 `\$`로 이스케이프해야 구분자로 오인되지 않는다
    """
    m = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", m)
    m = re.sub(r"_\{([^{}]*)\}", r"_(\1)", m)
    for cmd in ("times", "approx", "div", "cdot", "leq", "geq", "neq", "pm", "infinity"):
        m = m.replace("\\" + cmd, cmd)
    m = re.sub(r"(?<!\\)\$", r"\\$", m)  # 수식 내부의 맨 달러 기호 이스케이프

    # 천 단위 콤마가 든 숫자는 하나의 단위로 묶는다. 묶지 않으면 Typst가 콤마를
    # 구분자로 보아 `68,500/1.09^2` 를 `68, (500/1.09^2)` 로 조판한다.
    m = re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", lambda x: f'"{x.group(0)}"', m)

    # Typst 수식은 두 글자 이상의 알파벳을 변수명으로 해석해 "unknown variable"을
    # 낸다. PV·FV·FVIF 같은 재무 기호는 문자열로 감싸 그대로 출력한다.
    safe = {
        "times", "approx", "div", "cdot", "leq", "geq", "neq", "pm", "infinity",
        "frac", "sqrt", "log", "ln", "exp", "sin", "cos", "tan", "max", "min",
        "sum", "prod", "dots", "text", "upright", "abs", "floor", "ceil",
    }
    m = re.sub(
        r"(?<![\\\"A-Za-z0-9])[A-Za-z]{2,}(?![A-Za-z0-9\"])",
        lambda x: x.group(0) if x.group(0) in safe else f'"{x.group(0)}"',
        m,
    )
    return m


def repair_inline_math(line: str) -> str:
    r"""marker가 만든 수식 구분자 오류를 복구.

    marker는 인라인 수식 안의 달러 금액을 이스케이프하지 않아
    `$$100 \times 1.10 = $110$` / `$1 + r = $1,350/$1,250 = 1.08$` 처럼
    통화 기호가 수식 구분자로 오인되는 줄을 만든다. 이스케이프되지 않은 `$`를
    왼쪽부터 훑으며 수식 안/밖 상태를 추적하고, 수식 안에서 숫자가 바로 뒤따르는
    `$`(뒤에 닫는 구분자가 더 남아 있는 경우)는 금액으로 보아 이스케이프한다.
    """
    pos = [m.start() for m in re.finditer(r"(?<!\\)\$", line)]
    if len(pos) < 2:
        return line
    out, prev, in_math = [], 0, False
    for k, idx in enumerate(pos):
        out.append(line[prev:idx])
        nxt = line[idx + 1] if idx + 1 < len(line) else ""
        if in_math and nxt.isdigit() and k < len(pos) - 1:
            out.append("\\$")          # 수식 안의 금액
        else:
            out.append("$")            # 구분자
            in_math = not in_math
        prev = idx + 1
    out.append(line[prev:])
    return "".join(out)


def escape_markup(s: str) -> str:
    """Typst 마크업에서 특별한 의미를 갖는 문자를 이스케이프."""
    for ch in ("@", "#", "~"):
        s = s.replace(ch, "\\" + ch)
    return s


MD_DIR = Path(".")          # 이미지 경로 해석 기준 (main에서 설정)
TEXT_WIDTH_PT = 470.0       # A4 - 좌우 여백 2.2cm
EXTRACT_DPI = 150.0         # marker가 이미지를 뽑아내는 대략적 해상도


def image_size(path: str) -> tuple[int, int] | None:
    """PNG/JPEG 헤더에서 픽셀 크기를 읽는다 (외부 의존성 없이)."""
    f = MD_DIR / path
    try:
        data = f.read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":  # JPEG: SOF 마커 탐색
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(data[i + 2:i + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            i += 2 + seg
    return None


def convert_image(alt: str, path: str) -> str:
    """이미지 → #figure. 원본 픽셀 크기에 비례한 폭으로 배치한다.

    모두 전폭(100%)으로 넣으면 본문에 섞인 작은 아이콘까지 한 페이지를
    차지해 분량이 부풀고 가독성이 떨어진다.
    """
    caption = convert_inline(alt) if alt else ""
    size = image_size(path)
    if size:
        pt = size[0] * 72.0 / EXTRACT_DPI
        width = "100%" if pt >= TEXT_WIDTH_PT else f"{pt:.0f}pt"
    else:
        width = "100%"
    if caption:
        return f'#figure(image("{path}", width: {width}), caption: [{caption}])'
    return f'#figure(image("{path}", width: {width}))'


BULLET_RE = re.compile(r"^\s*(?:[-•▪·*\u2022]|\d+[.)])\s*\S")


def reflow_cell(cell: str) -> str:
    """셀 안의 <br>를 정리한다.

    marker가 PDF의 물리적 줄바꿈을 <br>로 옮겨 놓기 때문에 문장이 중간에서
    끊긴다. 불릿(-, ▪, 1.)으로 시작하는 조각 앞에서만 줄바꿈을 유지하고,
    나머지는 공백으로 이어 붙여 한 문장으로 복원한다.
    """
    parts = [p.strip() for p in re.split(r"<br\s*/?>", cell)]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    out = ""
    pending = ""  # 기호만 따로 떨어진 불릿을 다음 조각에 붙인다
    for frag in parts:
        if re.fullmatch(r"[-•▪·*\u2022]", frag):
            pending = frag
            continue
        if pending:
            out += ("<br>" if out else "") + pending + " " + frag
            pending = ""
        elif not out:
            out = frag
        elif BULLET_RE.match(frag):
            out += "<br>" + frag
        else:
            out += " " + frag
    if pending:
        out += ("<br>" if out else "") + pending
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def column_widths(rows: list[list[str]], ncols: int) -> str:
    """열별 최대 글자수에 비례해 너비를 배분. 짧은 열은 auto로 둔다."""
    lens = []
    for j in range(ncols):
        longest = max((len(r[j]) for r in rows), default=0)
        lens.append(longest)
    weights = [math.sqrt(w) for w in lens]
    long_idx = [j for j, w in enumerate(lens) if w > 14]
    base = min(weights[j] for j in long_idx) if long_idx else 1.0
    spec = []
    for j, w in enumerate(lens):
        if w <= 14:
            spec.append("auto")
        else:
            spec.append(f"{max(round(weights[j] / base, 2), 1.0)}fr")
    return "(" + ", ".join(spec) + ")"


def convert_table(block_lines: list[str]) -> str:
    """마크다운 표 → Typst #table (헤더 반복, 폭 자동 배분, 셀 재정렬)."""
    rows: list[list[str]] = []
    sep_after_first = False
    seen_data = 0
    for ln in block_lines:
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", ln):  # 구분 행
            if seen_data == 1:
                sep_after_first = True
            continue
        cells = [reflow_cell(c.strip()) for c in ln.strip("|").split("|")]
        rows.append(cells)
        seen_data += 1
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]

    def cell(c: str) -> str:
        return f"[{convert_inline(c)}]"

    def looks_like_header(cells: list[str]) -> bool:
        filled = [c.strip() for c in cells if c.strip()]
        if not filled:
            return False
        numeric = sum(1 for c in filled if re.fullmatch(r"[\d\s%.,\-–~/]+", c))
        return numeric < max(1, len(filled) // 2)

    has_header = sep_after_first and looks_like_header(rows[0])
    body_rows = rows[1:] if has_header else rows
    if has_header:
        # 페이지마다 반복된 헤더 행이 본문 행으로 섞여 들어온 것을 제거
        body_rows = [r for r in body_rows if r != rows[0]]

    lines = [
        "#block(breakable: true)[",
        "  #set text(size: 9pt)",
        "  #set par(justify: false, leading: 0.6em)",
        "  #table(",
        f"    columns: {column_widths(rows, ncols)},",
        "    stroke: 0.4pt + rgb(\"#bfbfbf\"),",
        "    inset: (x: 6pt, y: 5pt),",
        "    align: left + top,",
    ]
    if has_header:
        lines.append("    table.header(" + ", ".join(f"strong{cell(c)}" for c in rows[0]) + "),")
        lines.append("    fill: (x, y) => if y == 0 { rgb(\"#f0f0f0\") },")
    for r in body_rows:
        lines.append("    " + ", ".join(cell(c) for c in r) + ",")
    lines += ["  )", "]", ""]
    return "\n".join(lines)


def convert_markdown(md: str) -> str:
    """블록 단위로 마크다운 → Typst 변환."""
    lines = md.splitlines()
    out = []
    i = 0
    in_code = False
    code_lang = ""

    while i < len(lines):
        line = lines[i]
        if "$" in line and not line.strip().startswith("$$"):
            line = repair_inline_math(line)

        # 메타 주석 제거
        if re.match(r"\s*<!--\s*meta:.*?-->\s*$", line):
            i += 1
            continue

        # DONE 마커 제거
        if line.strip() == "<!-- DONE -->":
            i += 1
            continue

        # 코드블록
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                out.append(f"```{code_lang}" if code_lang else "```")
            else:
                in_code = False
                out.append("```")
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue

        # 블록 수식 $$...$$
        if line.strip().startswith("$$"):
            # 한 줄 내 종결 여부
            stripped = line.strip()
            if stripped.endswith("$$") and len(stripped) > 2 and stripped != "$$":
                content = convert_math(stripped[2:-2])
                out.append(f"$ {content} $")
                i += 1
                continue
            # 다중 라인
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().endswith("$$"):
                block.append(lines[i])
                i += 1
            content = convert_math("\n".join(block))
            out.append(f"$ {content} $")
            i += 1
            continue

        # 헤더
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            title = convert_inline(m.group(2))
            out.append("=" * level + " " + title)
            i += 1
            continue

        # 이미지 (단독 라인)
        m = re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if m:
            out.append(convert_image(m.group(1), m.group(2)))
            i += 1
            continue

        # 표 블록. marker는 원문 PDF의 페이지 경계마다 같은 표를 여러 블록으로
        # 쪼개 놓기 때문에, 빈 줄만 사이에 둔 같은 열 수의 표는 하나로 합친다.
        if line.startswith("|"):
            block = []
            while True:
                while i < len(lines) and lines[i].startswith("|"):
                    block.append(lines[i])
                    i += 1
                ncols_here = max(l.count("|") for l in block)
                j = i
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if (
                    j < len(lines)
                    and lines[j].startswith("|")
                    and lines[j].count("|") == ncols_here
                ):
                    i = j
                    continue
                break
            out.append(convert_table(block))
            continue

        # 리스트
        m = re.match(r"^(\s*)[-*]\s+(.+)$", line)
        if m:
            indent = m.group(1)
            content = convert_inline(m.group(2))
            out.append(f"{indent}- {content}")
            i += 1
            continue
        m = re.match(r"^(\s*)\d+\.\s+(.+)$", line)
        if m:
            indent = m.group(1)
            content = convert_inline(m.group(2))
            out.append(f"{indent}+ {content}")
            i += 1
            continue

        # 일반 텍스트 (인라인 변환)
        out.append(convert_inline(line))
        i += 1

    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--meta-title", default="")
    p.add_argument("--meta-orig-title", default="")
    p.add_argument("--meta-authors", default="")
    p.add_argument("--meta-source", default="")
    p.add_argument("--meta-translation-date", default=dt.date.today().isoformat())
    args = p.parse_args()

    global MD_DIR
    MD_DIR = args.input.resolve().parent
    md_text = args.input.read_text(encoding="utf-8")
    body_typst = convert_markdown(md_text)

    # 템플릿 import. Typst는 절대 경로를 프로젝트 루트 기준으로 해석하므로
    # body.typ 위치에서의 상대 경로로 계산한다.
    template_abs = (
        Path(__file__).resolve().parent.parent / "templates" / "paper.typ"
    )
    template_path = os.path.relpath(template_abs, args.output.resolve().parent)

    output = f"""#import "{template_path}": paper

#show: paper.with(
  title: "{args.meta_title}",
  orig_title: "{args.meta_orig_title}",
  authors: "{args.meta_authors}",
  source: "{args.meta_source}",
  translation_date: "{args.meta_translation_date}",
)

{body_typst}
"""
    args.output.write_text(output, encoding="utf-8")
    print(f"OK body.typ={args.output}")


if __name__ == "__main__":
    main()

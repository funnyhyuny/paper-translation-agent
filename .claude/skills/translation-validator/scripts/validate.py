#!/usr/bin/env python3
"""번역 결과를 규칙 기반으로 검증한다.

Usage:
    python validate.py <sections_dir> <sections_kr_dir>

종료 코드: 0=통과, 1=실패, 2=시스템 오류
"""

import json
import re
import sys
from pathlib import Path


LENGTH_RATIO_MIN = 0.6
LENGTH_RATIO_MAX = 1.2

META_PATTERN = re.compile(r"<!--\s*meta:\s*(\{.*?\})\s*-->")
IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")
BLOCK_MATH_PATTERN = re.compile(r"\$\$.+?\$\$", re.DOTALL)
INLINE_MATH_PATTERN = re.compile(r"(?<!\$)\$(?!\$)[^\n$]+?\$(?!\$)")
DONE_MARKER = "<!-- DONE -->"


def parse_meta(text: str) -> dict:
    m = META_PATTERN.search(text)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def strip_for_length(text: str) -> str:
    """길이 비교용 정제: 메타 주석, 수식, 이미지 참조 제거."""
    text = META_PATTERN.sub("", text)
    text = BLOCK_MATH_PATTERN.sub("", text)
    text = INLINE_MATH_PATTERN.sub("", text)
    text = IMAGE_PATTERN.sub("", text)
    return text.strip()


def count_math(text: str) -> tuple[int, int]:
    """(블록, 인라인) 수식 개수."""
    # 인라인은 블록 제거 후 계산
    no_block = BLOCK_MATH_PATTERN.sub("", text)
    return (
        len(BLOCK_MATH_PATTERN.findall(text)),
        len(INLINE_MATH_PATTERN.findall(no_block)),
    )


def check_done_marker(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return bool(lines) and lines[-1].strip() == DONE_MARKER


def check_markdown_syntax(text: str) -> list[str]:
    errors = []
    # 코드블록 짝수
    if text.count("```") % 2 != 0:
        errors.append("unmatched ``` fence")
    # 이미지/링크 괄호 균형 (단순 체크)
    open_brackets = text.count("[")
    close_brackets = text.count("]")
    if open_brackets != close_brackets:
        errors.append(f"bracket imbalance: [={open_brackets} ]={close_brackets}")
    open_parens = sum(1 for _ in re.finditer(r"\]\(", text))
    if open_parens > 0 and text.count(")") < open_parens:
        errors.append("link/image missing closing paren")
    # 표 행 파이프 일관성
    table_blocks = re.findall(r"(^\|.+\|$\n(?:^\|.+\|$\n?)+)", text, re.MULTILINE)
    for block in table_blocks:
        rows = [r for r in block.strip().splitlines() if r.startswith("|")]
        if len(rows) < 2:
            continue
        header_pipes = rows[0].count("|")
        for r in rows[1:]:
            if r.count("|") != header_pipes:
                errors.append(f"table row pipe count mismatch (expected {header_pipes})")
                break
    return errors


def validate_pair(src_path: Path, kr_path: Path) -> dict:
    errors = []
    src_text = src_path.read_text(encoding="utf-8")
    src_meta = parse_meta(src_text)

    # translate=false면 검증 스킵
    if src_meta.get("translate") is False:
        return {"ok": True, "skipped": "translate=false"}

    if not kr_path.exists():
        return {"ok": False, "errors": [f"missing translation file: {kr_path.name}"]}

    kr_text = kr_path.read_text(encoding="utf-8")

    # 1. DONE 마커
    if not check_done_marker(kr_text):
        errors.append("missing or malformed <!-- DONE --> marker on last line")

    # 2. 이미지 개수
    src_imgs = len(IMAGE_PATTERN.findall(src_text))
    kr_imgs = len(IMAGE_PATTERN.findall(kr_text))
    if src_imgs != kr_imgs:
        errors.append(f"image count mismatch: src={src_imgs} kr={kr_imgs}")

    # 3. 수식 개수
    src_block, src_inline = count_math(src_text)
    kr_block, kr_inline = count_math(kr_text)
    if src_block != kr_block:
        errors.append(f"block math count mismatch: src={src_block} kr={kr_block}")
    if src_inline != kr_inline:
        errors.append(f"inline math count mismatch: src={src_inline} kr={kr_inline}")

    # 4. 길이 비율
    src_len = len(strip_for_length(src_text))
    kr_len = len(strip_for_length(kr_text))
    if src_len > 0:
        ratio = kr_len / src_len
        if not (LENGTH_RATIO_MIN <= ratio <= LENGTH_RATIO_MAX):
            errors.append(f"length ratio {ratio:.2f} out of [{LENGTH_RATIO_MIN}, {LENGTH_RATIO_MAX}]")

    # 5. 마크다운 문법
    errors.extend(check_markdown_syntax(kr_text))

    return {"ok": not errors, "errors": errors} if errors else {"ok": True}


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    src_dir = Path(sys.argv[1])
    kr_dir = Path(sys.argv[2])

    if not src_dir.is_dir() or not kr_dir.is_dir():
        print(f"[validate] 디렉토리 누락: {src_dir} 또는 {kr_dir}", file=sys.stderr)
        sys.exit(2)

    results = {}
    failed = []
    src_files = sorted(src_dir.glob("sec_*.md"))
    for src_path in src_files:
        # 대응되는 kr 파일명: sec_0.md → sec_0_kr.md
        kr_path = kr_dir / f"{src_path.stem}_kr.md"
        result = validate_pair(src_path, kr_path)
        results[src_path.stem] = result
        if not result.get("ok"):
            failed.append(src_path.stem)

    results["summary"] = {
        "total": len(src_files),
        "passed": len(src_files) - len(failed),
        "failed": failed,
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""마크다운을 H1/H2 헤더 기준으로 섹션 파일로 분할한다.

Usage:
    python split.py <source.md> <sections_dir>

규칙:
- H1/H2 경계로 1차 분할 → sec_0.md, sec_1.md, ...
- 6000단어 초과 섹션은 H3 기준 이차 분할 → sec_N_a.md, sec_N_b.md
- References/Bibliography/참고문헌 섹션은 translate=false 메타 부여
"""

import json
import re
import sys
from pathlib import Path


LONG_SECTION_WORD_THRESHOLD = 6000
REFERENCES_TITLES = {
    "references", "reference", "bibliography",
    "참고문헌", "참고 문헌", "참고자료",
}


def split_by_heading(text: str, level: int) -> list[tuple[str, str]]:
    """주어진 헤딩 레벨로 분할. [(title, body_including_heading), ...] 반환.

    헤더가 없으면 [("", text)] 반환.
    """
    pattern = re.compile(rf"^({'#' * level}) (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]

    chunks = []
    # 첫 매칭 이전 텍스트(전문, 초록 등)는 sec_0 전에 별도 섹션으로 보존
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            chunks.append(("__preamble__", preamble))

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(2).strip()
        body = text[m.start() : end].rstrip()
        chunks.append((title, body))

    return chunks


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def is_references_title(title: str) -> bool:
    return title.strip().lower() in REFERENCES_TITLES


def write_section(path: Path, body: str, meta: dict) -> None:
    meta_line = f"<!-- meta: {json.dumps(meta, ensure_ascii=False)} -->\n"
    path.write_text(meta_line + body + "\n", encoding="utf-8")


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    text = src.read_text(encoding="utf-8")

    # H2 기준 우선, 없으면 H1
    chunks = split_by_heading(text, level=2)
    if len(chunks) <= 1:
        chunks = split_by_heading(text, level=1)

    written = []
    if len(chunks) <= 1:
        # 헤더 부족: 단일 섹션
        print("[split] 헤더가 부족하여 전체를 단일 섹션으로 처리", file=sys.stderr)
        path = out_dir / "sec_0.md"
        write_section(path, text, {"index": 0, "title": "(untitled)", "translate": True})
        written.append(str(path))
    else:
        idx = 0
        for title, body in chunks:
            if title == "__preamble__":
                # 전문은 sec_0로 강제 (이후 메인 섹션은 sec_1부터)
                path = out_dir / "sec_0.md"
                write_section(
                    path, body,
                    {"index": 0, "title": "Preamble", "translate": True},
                )
                written.append(str(path))
                idx = 1
                continue

            translate = not is_references_title(title)

            # 장문이면 H3 분할
            if translate and word_count(body) > LONG_SECTION_WORD_THRESHOLD:
                subchunks = split_by_heading(body, level=3)
                if len(subchunks) > 1:
                    for sub_i, (sub_title, sub_body) in enumerate(subchunks):
                        suffix = chr(ord("a") + sub_i)
                        path = out_dir / f"sec_{idx}_{suffix}.md"
                        write_section(
                            path, sub_body,
                            {"index": idx, "subindex": sub_i, "title": f"{title} / {sub_title}", "translate": True},
                        )
                        written.append(str(path))
                    idx += 1
                    continue

            path = out_dir / f"sec_{idx}.md"
            write_section(
                path, body,
                {"index": idx, "title": title, "translate": translate, **({"type": "references"} if not translate else {})},
            )
            written.append(str(path))
            idx += 1

    if len(written) < 2:
        print(f"[split] 경고: 섹션 1개만 생성됨 (병렬화 스킵)", file=sys.stderr)

    print(f"OK sections={len(written)}")
    for p in written:
        print(p)


if __name__ == "__main__":
    main()

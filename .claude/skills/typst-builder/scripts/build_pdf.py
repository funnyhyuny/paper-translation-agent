#!/usr/bin/env python3
"""Typst 본문 파일을 컴파일하여 PDF 생성.

Usage:
    python build_pdf.py <body.typ> <out.pdf>
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    body = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()

    if not body.exists():
        print(f"[build] 입력 .typ 파일 없음: {body}", file=sys.stderr)
        sys.exit(1)

    if shutil.which("typst") is None:
        print(
            "[build] typst 바이너리를 찾을 수 없음. 설치: brew install typst",
            file=sys.stderr,
        )
        sys.exit(3)

    out.parent.mkdir(parents=True, exist_ok=True)

    # 템플릿(.claude/skills/...)과 body가 모두 들어가는 디렉토리를 프로젝트 루트로 지정.
    # 지정하지 않으면 Typst가 body.typ 상위 디렉토리 밖의 템플릿 로드를 거부한다.
    project_root = Path(__file__).resolve().parents[4]
    try:
        root = Path(os.path.commonpath([project_root, body.parent]))
    except ValueError:
        root = body.parent

    cmd = ["typst", "compile", "--root", str(root), str(body), str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"[build] Typst 컴파일 실패", file=sys.stderr)
        sys.exit(result.returncode)

    if not out.exists():
        print(f"[build] PDF가 생성되지 않음: {out}", file=sys.stderr)
        sys.exit(4)

    print(f"OK pdf={out}")


if __name__ == "__main__":
    main()

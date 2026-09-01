#!/usr/bin/env python3
"""지정 페이지를 300 DPI 고해상도 PNG로 재추출한다.

Usage:
    python recrop.py <input.pdf> <page_number_1based> <output.png>

좌표를 받지 않는다. 페이지 전체를 PNG로 저장한다.
"""

import sys
from pathlib import Path

import fitz  # PyMuPDF


DPI = 300


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    page_num = int(sys.argv[2])  # 1-based
    dst = Path(sys.argv[3])
    dst.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(src)
    if page_num < 1 or page_num > doc.page_count:
        print(f"[recrop] 페이지 범위 초과: 1..{doc.page_count}", file=sys.stderr)
        sys.exit(2)

    page = doc.load_page(page_num - 1)
    pix = page.get_pixmap(dpi=DPI)
    pix.save(dst)
    doc.close()
    print(f"OK recrop={dst}")


if __name__ == "__main__":
    main()

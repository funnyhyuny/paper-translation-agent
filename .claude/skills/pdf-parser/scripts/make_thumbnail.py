#!/usr/bin/env python3
"""PDF의 모든 페이지를 격자 형태의 썸네일 시트 PDF로 묶는다.

Usage:
    python make_thumbnail.py <input.pdf> <output.pdf>

페이지당 약 200 DPI 썸네일, A4 1장에 3×3 격자.
"""

import sys
from pathlib import Path

import fitz  # PyMuPDF


GRID_COLS = 3
GRID_ROWS = 3
THUMB_DPI = 100  # 썸네일 해상도


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)

    src_doc = fitz.open(src)
    out_doc = fitz.open()

    # A4 사이즈 (포인트 단위)
    page_w, page_h = fitz.paper_size("a4")
    cell_w = page_w / GRID_COLS
    cell_h = page_h / GRID_ROWS

    per_sheet = GRID_COLS * GRID_ROWS
    for sheet_start in range(0, src_doc.page_count, per_sheet):
        sheet = out_doc.new_page(width=page_w, height=page_h)
        for i in range(per_sheet):
            idx = sheet_start + i
            if idx >= src_doc.page_count:
                break
            r = i // GRID_COLS
            c = i % GRID_COLS
            rect = fitz.Rect(
                c * cell_w + 5,
                r * cell_h + 15,
                (c + 1) * cell_w - 5,
                (r + 1) * cell_h - 5,
            )
            page = src_doc.load_page(idx)
            pix = page.get_pixmap(dpi=THUMB_DPI)
            sheet.insert_image(rect, pixmap=pix)
            # 페이지 번호 라벨
            sheet.insert_text(
                (c * cell_w + 8, r * cell_h + 12),
                f"p.{idx + 1}",
                fontsize=8,
            )

    out_doc.save(dst)
    out_doc.close()
    src_doc.close()
    print(f"OK thumbnail={dst}")


if __name__ == "__main__":
    main()

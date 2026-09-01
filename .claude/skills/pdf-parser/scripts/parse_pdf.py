#!/usr/bin/env python3
"""Marker로 PDF를 마크다운으로 변환하고 이미지를 추출한다.

Usage:
    python parse_pdf.py <input.pdf> <output_dir> [--force-ocr]

Output:
    <output_dir>/source.md
    <output_dir>/images/*.png
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


MIN_CHARS_PER_PAGE = 200


def run_marker(pdf_path: Path, work_dir: Path, force_ocr: bool = False) -> Path:
    """Marker 단일 PDF 변환 호출. 결과 디렉토리 경로 반환.

    force_ocr: 텍스트 레이어의 글리프 매핑이 깨진 PDF(숫자가 문장부호로
    추출되는 경우 등)에서 렌더링 이미지를 OCR해 본문을 다시 읽는다.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "marker_single",
        str(pdf_path),
        "--output_dir", str(work_dir),
        "--output_format", "markdown",
    ]
    if force_ocr:
        cmd.append("--force_ocr")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[parse_pdf] Marker 실패\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}", file=sys.stderr)
        sys.exit(2)
    # Marker는 <output_dir>/<pdf_stem>/ 아래에 결과 생성
    return work_dir / pdf_path.stem


def collect_outputs(marker_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    """Marker 결과를 우리 폴더 규약으로 재배치한다.

    - 마크다운 파일 → output_dir/source.md
    - 이미지 파일들 → output_dir/images/*
    """
    source_md = output_dir / "source.md"
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    md_candidates = list(marker_dir.glob("*.md"))
    if not md_candidates:
        print(f"[parse_pdf] 마크다운 출력이 없음: {marker_dir}", file=sys.stderr)
        sys.exit(3)
    shutil.copyfile(md_candidates[0], source_md)

    for img in marker_dir.iterdir():
        if img.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            shutil.copyfile(img, images_dir / img.name)

    return source_md, images_dir


def validate(source_md: Path, pdf_path: Path) -> None:
    """페이지당 문자 수가 너무 적으면 스캔본 의심으로 종료."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[parse_pdf] PyMuPDF가 설치되어 있지 않아 페이지 수 기반 검증을 스킵", file=sys.stderr)
        return
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    doc.close()
    text_len = len(source_md.read_text(encoding="utf-8"))
    avg = text_len / max(page_count, 1)
    if avg < MIN_CHARS_PER_PAGE:
        print(
            f"[parse_pdf] 페이지당 평균 문자수가 너무 적음 ({avg:.0f} < {MIN_CHARS_PER_PAGE}). "
            f"스캔본 PDF로 의심됨.",
            file=sys.stderr,
        )
        sys.exit(4)


def check_image_refs(source_md: Path, images_dir: Path) -> None:
    """마크다운 내 이미지 참조가 모두 파일로 존재하는지 확인."""
    import re

    md_text = source_md.read_text(encoding="utf-8")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_text)
    missing = []
    for ref in refs:
        name = Path(ref).name
        if not (images_dir / name).exists():
            missing.append(ref)
    if missing:
        print(f"[parse_pdf] 마크다운이 참조하는 이미지가 누락됨: {missing}", file=sys.stderr)
        sys.exit(5)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_ocr = "--force-ocr" in sys.argv or "--force_ocr" in sys.argv
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(args[0]).resolve()
    output_dir = Path(args[1]).resolve()

    if not pdf_path.exists():
        print(f"[parse_pdf] 입력 PDF를 찾을 수 없음: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    work_dir = output_dir / "_marker_raw"
    marker_dir = run_marker(pdf_path, work_dir, force_ocr=force_ocr)
    source_md, images_dir = collect_outputs(marker_dir, output_dir)
    validate(source_md, pdf_path)
    check_image_refs(source_md, images_dir)

    # 작업 디렉토리 정리
    shutil.rmtree(work_dir, ignore_errors=True)

    print(f"OK source.md={source_md} images={images_dir}")


if __name__ == "__main__":
    main()

---
name: pdf-parser
description: 영문 PDF를 마크다운으로 변환하고 그림/표 이미지를 추출하며, 페이지 썸네일 시트와 사용자 요청 시 페이지 재크롭을 수행한다. 워크플로우 [1]·[2] 단계 및 게이트 ① 재추출에서 사용.
---

# pdf-parser

영문 학술 PDF를 마크다운 + 이미지 자료로 분해한다. Marker(메인 파서)와 PyMuPDF(보조 도구)를 사용한다.

## 언제 사용

- 워크플로우 [1]: 영문 PDF → 마크다운 변환 (수식 LaTeX, 표는 마크다운, 그림 별도 파일)
- 워크플로우 [2]: 이미지 추출 + 페이지 썸네일 시트 생성
- 게이트 ①: 사용자가 페이지 번호를 지정하여 재추출 요청한 경우

## 제공 스크립트

| 스크립트 | 역할 | 호출 예시 |
|---------|------|----------|
| `scripts/parse_pdf.py` | PDF → 마크다운 + 이미지 추출 (Marker) | `python parse_pdf.py <input.pdf> <output_dir>` |
| `scripts/make_thumbnail.py` | 페이지 썸네일 격자 PDF 생성 (PyMuPDF) | `python make_thumbnail.py <input.pdf> <output_path>` |
| `scripts/recrop.py` | 지정 페이지를 고해상도 PNG로 재추출 | `python recrop.py <input.pdf> <page_num> <output_path>` |

## 사용 절차

### [1]·[2] 단계 (최초 파싱)

```bash
# 1. PDF → 마크다운 + 이미지
python .claude/skills/pdf-parser/scripts/parse_pdf.py \
  /input/<논문명>.pdf \
  /output/<논문명>_review

# 결과:
#   /output/<논문명>_review/source.md
#   /output/<논문명>_review/images/*.png

# 2. 검토용 썸네일 시트
python .claude/skills/pdf-parser/scripts/make_thumbnail.py \
  /input/<논문명>.pdf \
  /output/<논문명>_review/images/_thumbnail_sheet.pdf
```

### 게이트 ① 재추출 (페이지 단위 고해상도)

```bash
python .claude/skills/pdf-parser/scripts/recrop.py \
  /input/<논문명>.pdf \
  7 \
  /output/<논문명>_review/images/page_07_recrop.png
```

해상도는 300 DPI 고정. 사용자에게 좌표를 묻지 않는다.

## 검증

- `parse_pdf.py` 완료 후:
  - `source.md` 존재 확인
  - 페이지당 평균 문자수 ≥ 200 (미만이면 스캔본 의심 → 에스컬레이션)
  - 마크다운 내 `![](...)` 참조가 가리키는 파일이 `images/` 안에 모두 존재
- 누락 시 자동 재시도 1회 후에도 실패하면 사유 로그 후 게이트 ①로 진행.

## 참조 문서

- `references/marker_usage.md` — Marker 명령행 옵션, GPU/CPU 모드, 모델 캐시 경로

---
name: typst-builder
description: 통합 마크다운(merged_kr.md)을 Typst 소스로 변환하고 한국어 폰트(Noto Sans KR)가 적용된 템플릿에 주입해 최종 PDF로 컴파일한다. 워크플로우 [7] 단계 및 게이트 ② 수정 후 재빌드에서 사용.
---

# typst-builder

마크다운 → Typst → PDF 빌드 파이프라인. 한국어 폰트, 1단 조판, 그림 인라인 배치, 표지·목차·머리말/꼬리말을 포함한다.

## 언제 사용

- 워크플로우 [7]: `merged_kr.md`에서 최종 PDF 생성.
- 게이트 ② 수정 후 재빌드.

## 제공 스크립트 / 자산

| 자산 | 경로 |
|------|------|
| 마크다운→Typst 변환 | `scripts/md_to_typst.py` |
| Typst 컴파일 | `scripts/build_pdf.py` |
| 템플릿 | `templates/paper.typ` |

## 사용 절차

```bash
# 1. 마크다운 → Typst 소스
python .claude/skills/typst-builder/scripts/md_to_typst.py \
  /output/<논문명>_review/merged_kr.md \
  /output/<논문명>_review/body.typ \
  --meta-title "<논문 한국어 제목>" \
  --meta-orig-title "<English Title>" \
  --meta-authors "<저자>" \
  --meta-source "<원문 출처/연도>"

# 2. Typst 컴파일
python .claude/skills/typst-builder/scripts/build_pdf.py \
  /output/<논문명>_review/body.typ \
  /output/<논문명>_KR.pdf
```

`build_pdf.py`는 내부적으로 `paper.typ` 템플릿을 사용하여 body를 임포트한다.

## 템플릿 정책

- **단 구성**: 1단 고정.
- **그림/표 배치**: `figure()`의 placement 옵션을 사용하지 않음 → 본문 등장 순서 그대로 인라인.
- **그림 너비**: 전폭. 표는 본문 폭 안에 맞도록 자동 축소.
- **첨부**: 표지(한국어 제목 + 영문 제목 + 저자 + 원문 출처 + 번역일), 자동 목차, 머리말(논문 제목)/꼬리말(페이지 번호).
- **폰트**: 본문/제목 모두 Noto Sans KR. 모노스페이스는 시스템 기본.
- **References**: "참고문헌" 제목으로 원문 그대로 포함 (메타 `translate: false` 섹션의 내용을 그대로 임포트).

## 검증

- PDF 파일 생성 여부 확인
- 페이지 수가 원문 PDF의 ±30% 이내인지 (참조용, 정보 부족 시 스킵)
- Typst stderr에 fatal 에러 없음

실패 시 컴파일 로그를 살펴 마크다운에서 유발했을 가능성이 높은 패턴(짝 안 맞는 강조, 잘못된 표 등)을 메인 에이전트가 수정한 뒤 1회 재시도.

## 폰트 누락 처리

`paper.typ` 컴파일 시 Noto Sans KR이 시스템에 없으면 Typst가 경고를 출력한다. 메인 에이전트는 stderr에서 "font not found" 패턴을 발견하면 사용자에게:

```
[폰트 누락] Noto Sans KR이 설치되어 있지 않습니다.
설치: https://fonts.google.com/noto/specimen/Noto+Sans+KR
또는 프로젝트 폴더 ./fonts/ 에 .otf 파일을 두고 다시 시도하세요.
```

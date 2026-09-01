# 논문 번역 에이전트

영문 학술 논문 PDF를 한국어 PDF로 번역하는 Claude Code 파이프라인.

## 워크플로우

```
[입력 PDF]
  → [1] PDF → 마크다운        (pdf-parser 스킬)
  → [2] 이미지 추출           (pdf-parser 스킬)
  → [게이트 ①] 이미지 검토
  → [3] 용어집 추출           (메인 LLM)
  → [게이트 ③] 글로서리 검토 + 비용 안내
  → [4] 섹션 분할             (section-splitter 스킬)
  → [5] 병렬 번역             (translator 서브에이전트 × N)
  → [6] 취합 + 자기 검증      (translation-validator 스킬)
  → [7] Typst 빌드            (typst-builder 스킬)
  → [게이트 ②] 최종 검토
```

## 구성

| 경로 | 설명 |
|------|------|
| `CLAUDE.md` | 메인 오케스트레이터 지침 (7단계 워크플로우, 게이트 운영 규칙) |
| `paper-translation-agent-design.md` | 전체 설계 문서 |
| `.claude/agents/translator/` | 섹션 병렬 번역 서브에이전트 |
| `.claude/skills/pdf-parser/` | PDF → 마크다운 변환, 이미지 추출·재크롭 (marker-pdf, pymupdf) |
| `.claude/skills/section-splitter/` | 마크다운 섹션 분할 |
| `.claude/skills/translation-validator/` | 번역 결과 검증 |
| `.claude/skills/typst-builder/` | Typst 템플릿 기반 한국어 PDF 빌드 |
| `setup.sh` | 의존성 설치 (marker-pdf, pymupdf, Typst, Noto Sans KR) |

## 사용법

```bash
bash setup.sh          # 최초 1회 — 의존성 설치
mkdir -p input output  # 작업 폴더 생성
# input/ 에 영문 PDF를 넣고 Claude Code 실행
```

최종 산출물은 `output/<논문명>_KR.pdf`, 중간 산출물은 `output/<논문명>_review/`에 저장됩니다.

> `input/`, `output/`은 저장소에서 제외되어 있습니다.

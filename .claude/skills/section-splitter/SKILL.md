---
name: section-splitter
description: 통합 마크다운(source.md)을 H1/H2 헤더 기준으로 섹션 단위 파일로 분할한다. 장문 섹션은 H3로 이차 분할하며, References 섹션은 번역 제외 메타플래그를 단다. 워크플로우 [4] 단계에서 사용.
---

# section-splitter

번역 병렬화를 위한 섹션 분할기. 학술 논문의 자연스러운 경계(H2 위주)를 따라 마크다운을 쪼갠다.

## 언제 사용

- 워크플로우 [4]: 용어집 확정 후 `source.md`를 섹션별 파일로 분할.
- 게이트 ②에서 특정 섹션 통째 재번역이 필요할 때 (재분할은 보통 불필요, 기존 분할 결과 재사용)

## 제공 스크립트

| 스크립트 | 호출 |
|---------|------|
| `scripts/split.py` | `python split.py <source.md> <sections_dir>` |

## 동작 규칙

1. **H1/H2 헤더 기준 1차 분할**: `#` 또는 `##` 라인을 경계로 분리.
2. **장문 섹션 이차 분할**: 6000단어 초과 섹션은 H3(`###`) 기준으로 재분할. 결과 파일명: `sec_3_a.md`, `sec_3_b.md` 등.
3. **References 처리**: 제목이 `References`, `Bibliography`, `참고문헌` 등인 섹션은:
   - 파일 첫 줄에 `<!-- meta: {"translate": false, "type": "references"} -->` 메타 주석 추가
   - 번역 단계에서 스킵됨, 빌드 단계에서 원문 그대로 첨부
4. **출력 위치**: `<sections_dir>/sec_0.md`, `sec_1.md`, ... 순번은 원문 등장 순서.

## 출력 형식 (각 파일 헤더)

```markdown
<!-- meta: {"index": 3, "title": "Methods", "translate": true} -->
## Methods

본문 내용...
```

## 성공 기준

- 최소 2개 이상의 섹션 파일 생성.
- 모든 섹션에 메타 주석이 존재.
- 헤더가 부족한 PDF(예: H1/H2 없음)인 경우 전체를 단일 섹션 `sec_0.md`로 처리하고 stderr에 경고 출력 (병렬화 스킵).

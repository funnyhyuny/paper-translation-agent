# Marker 사용 참고

본 프로젝트는 [Marker](https://github.com/VikParuchuri/marker)를 통한 PDF→마크다운 변환을 전제로 한다.

## 설치

```bash
pip install marker-pdf
```

최초 실행 시 모델 가중치(수 GB)를 자동 다운로드한다. 시간이 걸리므로 첫 논문 처리에는 여유를 두자.

## 단일 PDF 변환

```bash
marker_single <input.pdf> --output_dir <out_dir> --output_format markdown
```

결과는 `<out_dir>/<pdf_stem>/` 아래에 생성된다:
- `<pdf_stem>.md` — 마크다운
- `*.png` 또는 `*.jpg` — 추출된 그림/표 이미지

## GPU vs CPU

- CUDA 가능한 환경에서는 자동으로 GPU 사용 (수십 배 빠름)
- CPU 모드도 동작하지만 페이지당 수 분 소요
- 환경 변수 `TORCH_DEVICE=cpu`로 강제 가능

## 흔한 이슈

| 증상 | 원인 / 대처 |
|------|-------------|
| 페이지당 텍스트가 거의 없음 | 스캔본 PDF — 본 시스템은 명시적으로 거부 |
| 표가 깨짐 | Marker의 표 인식 한계. 게이트 ②에서 사용자가 마크다운 직접 수정 권장 |
| 수식이 일반 텍스트로 변환 | PDF에 임베드된 수식 폰트 누락. 게이트 ②에서 LaTeX로 수동 보정 |
| 이미지가 너무 작음/잘림 | `recrop.py`로 페이지 전체 PNG 재추출 |

## 모델 캐시 경로

기본값: `~/.cache/datalab/` (변경하려면 `MARKER_MODEL_DIR` 환경 변수)

# ILOVEYELIN2 Mac 앱 설계

## 목표
번역 파이프라인을 모르는 사용자가 M1 노트북에서 터미널 없이 쓴다. PDF를 input 폴더나 앱 창에 넣으면 output 폴더에 한국어 PDF가 나온다.

## 결정 사항
- 대상: Apple Silicon, macOS 13 이상. 인증은 사용자의 Claude 구독 로그인.
- 흐름: 완전 자동(게이트 없음). 한 번에 한 파일. 끝난 원본은 `input/완료`, 처리 불가 원본은 `input/실패`로 이동.
- 구성: SwiftUI 앱 + `engine/pipeline.py` + `engine/setup.sh`. 앱에는 스크립트, uv, Typst를 포함하고 Python 환경, PDF 모델, Claude Code는 첫 실행 때 설치한다.
- 디자인: "종이 책상". 크림색 종이, 명조체 제목, 적갈색 포인트. 화면은 준비, 대기, 번역 중, 완료, 멈춤.

## 폴더
- 사용자: `~/Documents/ILOVEYELIN2/{input,output}`
- 내부: `~/Library/Application Support/ILOVEYELIN2/` (venv, 도구, 작업 폴더 `work/<이름>-<해시>`)

## 파이프라인
parse → glossary → split → clean → translate → validate → merge → build. 단계 완료는 `progress.log`에 기록하며, 재시작하면 완료 단계를 건너뛴다.

- Claude 호출: `claude -p`, 도구 없음, 설정·MCP·슬래시 명령 격리. 입력과 출력은 텍스트로 주고받는다. 격리하지 않으면 호출당 약 16만 토큰이 든다.
- 동시 번역 3개. 4000단어 초과 섹션은 문단 단위로 다시 나눈다.
- clean: 깨진 수식 문자나 붙은 단어가 있는 섹션만 복구한다. 이미지 수나 길이가 크게 변하면 복구를 버린다.
- 검증: 실패 섹션만 1회 재번역. 완료 표시, 이미지, 수식 개수 오류가 남으면 멈추고, 그 외 오류는 "확인 필요"로 남기고 PDF를 만든다.
- 수식 조판은 mitex를 먼저 쓰고 컴파일 실패 시 기본 변환으로 재시도한다.
- 생략: 섹션 경계 LLM 검토, 글로서리 자동 치환(병기 규칙과 충돌 위험).

## 오류
pipeline은 JSON 줄로 상태를 보고한다. rate_limit, auth, network, verify, build, failed는 원본을 유지하고 사용자가 이어서 실행한다. scanned는 `input/실패`로 옮긴다.

## 버전 고정
PyTorch 2.12는 macOS 14 이상 전용이라 2.11.0으로 고정한다. 나머지는 `engine/requirements.lock`을 따른다.

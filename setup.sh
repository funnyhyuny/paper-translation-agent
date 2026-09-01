#!/usr/bin/env bash
# 논문 번역 파이프라인 의존성 설치 스크립트
# 실행: bash setup.sh

set -e

echo "==> 1. Python 패키지 설치 (marker-pdf, pymupdf)"
if command -v pip3 >/dev/null 2>&1; then
  pip3 install --upgrade marker-pdf pymupdf
else
  echo "pip3가 없습니다. Python 3.9+를 먼저 설치하세요." >&2
  exit 1
fi

echo "==> 2. Typst 설치 여부 확인"
if command -v typst >/dev/null 2>&1; then
  echo "    Typst 이미 설치됨: $(typst --version)"
else
  echo "    Typst가 없습니다."
  if command -v brew >/dev/null 2>&1; then
    echo "    Homebrew로 설치 중..."
    brew install typst
  else
    echo "    Homebrew가 없습니다. https://github.com/typst/typst/releases 에서 바이너리를 직접 다운로드하세요." >&2
    exit 2
  fi
fi

echo "==> 3. Noto Sans KR 폰트 확인"
if fc-list 2>/dev/null | grep -qi "noto sans kr"; then
  echo "    Noto Sans KR 설치됨"
elif ls ~/Library/Fonts/NotoSansKR* >/dev/null 2>&1 || \
     ls /Library/Fonts/NotoSansKR* >/dev/null 2>&1 || \
     ls /System/Library/Fonts/NotoSansKR* >/dev/null 2>&1; then
  echo "    Noto Sans KR이 macOS 폰트 디렉토리에 존재"
else
  echo "    [경고] Noto Sans KR이 설치되어 있지 않습니다."
  echo "    https://fonts.google.com/noto/specimen/Noto+Sans+KR 에서 다운받아 설치하세요."
  echo "    (Typst가 'font not found' 에러를 내면 이 단계로 돌아오세요)"
fi

echo ""
echo "==> 4. Marker 모델 캐시 사전 다운로드 (선택)"
echo "    최초 PDF 변환 시 자동 다운로드되지만, 미리 받아두려면 작은 PDF를 한 번 처리하세요."

echo ""
echo "셋업 완료. /input/ 폴더에 영문 PDF를 두고 Claude Code를 시작하세요."

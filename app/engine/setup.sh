#!/bin/bash
# ILOVEYELIN2 첫 실행 준비. 단계별 상태를 JSON 한 줄씩 보고하고, 끝난 단계는 다시 실행하지 않는다.
# 환경 변수: ILY_SUPPORT(내부 폴더), ILY_BIN(앱에 포함된 uv, typst 위치)
set -uo pipefail

SUP="${ILY_SUPPORT:-$HOME/Library/Application Support/ILOVEYELIN2}"
ENGINE="$(cd "$(dirname "$0")" && pwd)"
SRC_BIN="${ILY_BIN:-$ENGINE/../bin}"
BIN="$SUP/bin"
VENV="$SUP/venv"
STAMPS="$SUP/stamps"
LOG="$SUP/setup.log"
LOCK_HASH="$(shasum -a 256 "$ENGINE/requirements.lock" | cut -c1-12)"
MODELS="$HOME/Library/Caches/datalab"

mkdir -p "$BIN" "$STAMPS"
export PATH="$BIN:$VENV/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export UV_PYTHON_INSTALL_DIR="$SUP/python" UV_CACHE_DIR="$SUP/uv-cache" UV_PYTHON_PREFERENCE=only-managed

emit() { printf '{"event":"step","id":"%s","status":"%s"}\n' "$1" "$2"; }

fail() {
  printf '{"event":"error","id":"%s","log":"%s"}\n' "$1" "$LOG"
  exit 1
}

# 실패 시 1회 재시도한다. 끝난 단계는 건너뛴다.
step() {
  local id="$1" stamp="$STAMPS/$2" fn="$3"
  if [ -f "$stamp" ]; then emit "$id" done; return; fi
  emit "$id" running
  if "$fn" >>"$LOG" 2>&1 || "$fn" >>"$LOG" 2>&1; then
    touch "$stamp"
    emit "$id" done
  else
    fail "$id"
  fi
}

install_tools() {
  cp -f "$SRC_BIN/uv" "$SRC_BIN/typst" "$BIN/" &&
    chmod +x "$BIN/uv" "$BIN/typst" &&
    { xattr -d com.apple.quarantine "$BIN/uv" "$BIN/typst" 2>/dev/null || true; }
}

install_python() {
  rm -rf "$VENV"
  uv venv --python 3.12 "$VENV" &&
    uv pip install --python "$VENV/bin/python" -r "$ENGINE/requirements.lock" &&
    { uv cache clean || true; }
}

report_model_size() {
  while sleep 3; do
    [ -d "$MODELS" ] || continue
    printf '{"event":"progress","id":"models","mb":%s}\n' "$(( $(du -sk "$MODELS" | cut -f1) / 1024 ))"
  done
}

install_models() {
  TORCH_DEVICE=cpu "$VENV/bin/python" -c "from marker.models import create_model_dict; create_model_dict()"
}

run_models_step() {
  report_model_size &
  local reporter=$!
  step models "models" install_models
  kill "$reporter" 2>/dev/null
  wait "$reporter" 2>/dev/null
}

install_typst_packages() {
  local dir
  dir="$(mktemp -d)"
  printf '#import "@preview/mitex:0.2.6": mi, mitex\n#mitex(`x^2`)\n' >"$dir/warm.typ"
  typst compile "$dir/warm.typ" "$dir/warm.pdf"
  local rc=$?
  rm -rf "$dir"
  return $rc
}

find_claude() { command -v claude >/dev/null 2>&1; }

install_claude() {
  find_claude || { curl -fsSL https://claude.ai/install.sh | bash; }
  find_claude
}

step tools "tools" install_tools
step python "python-$LOCK_HASH" install_python
run_models_step
step typst "typst-packages" install_typst_packages
step claude "claude" install_claude
printf '{"event":"finished"}\n'

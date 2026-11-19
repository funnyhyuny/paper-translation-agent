#!/bin/bash
# ILOVEYELIN2.app을 빌드하고 전달용 zip을 만든다. 실행: bash app/build.sh
# 결과: app/dist/ILOVEYELIN2.app, app/dist/ILOVEYELIN2.zip
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$APP_DIR")"
BUILD="$APP_DIR/build"
DIST="${DIST:-$APP_DIR/dist}"
VENDOR="$BUILD/vendor"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
# Desktop 폴더는 파일 속성을 다시 붙여 서명을 막으므로 임시 폴더에서 조립한다.
BUNDLE="$STAGE/ILOVEYELIN2.app"
RES="$BUNDLE/Contents/Resources"
UV_VERSION="0.13.7"
TYPST_VERSION="0.14.2"
# app/VERSION: 첫 줄 표시 버전, 둘째 줄 빌드 번호(업데이트 비교에 사용)
APP_VERSION="${APP_VERSION:-$(sed -n 1p "$APP_DIR/VERSION")}"
BUILD_NUMBER="${BUILD_NUMBER:-$(sed -n 2p "$APP_DIR/VERSION")}"

fetch_vendor() {
  mkdir -p "$VENDOR"
  if [ ! -x "$VENDOR/uv" ]; then
    curl -fsSL "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz" |
      tar -xz -C "$VENDOR" --strip-components=1 uv-aarch64-apple-darwin/uv
  fi
  if [ ! -x "$VENDOR/typst" ]; then
    curl -fsSL "https://github.com/typst/typst/releases/download/v$TYPST_VERSION/typst-aarch64-apple-darwin.tar.xz" |
      tar -xJ -C "$VENDOR" --strip-components=1 typst-aarch64-apple-darwin/typst
  fi
}

fetch_vendor
[ "${1:-}" = "--vendor-only" ] && exit 0

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS" "$RES/bin" "$RES/engine/skills" "$RES/engine/agents"

swiftc -parse-as-library -swift-version 5 -O -target arm64-apple-macos13.0 \
  "$APP_DIR"/Sources/*.swift -o "$BUNDLE/Contents/MacOS/ILOVEYELIN2"

if [ ! -f "$BUILD/AppIcon.icns" ]; then
  swiftc -target arm64-apple-macos13.0 "$APP_DIR/make_icon.swift" -o "$BUILD/make_icon"
  rm -rf "$BUILD/AppIcon.iconset"
  "$BUILD/make_icon" "$BUILD/AppIcon.iconset"
  iconutil -c icns "$BUILD/AppIcon.iconset" -o "$BUILD/AppIcon.icns"
fi
cp "$BUILD/AppIcon.icns" "$RES/AppIcon.icns"

cp "$VENDOR/uv" "$VENDOR/typst" "$RES/bin/"
cp "$APP_DIR/engine/pipeline.py" "$APP_DIR/engine/setup.sh" "$APP_DIR/engine/requirements.lock" "$RES/engine/"
cp -R "$ROOT/.claude/agents/translator" "$RES/engine/agents/"
for skill in pdf-parser section-splitter translation-validator typst-builder; do
  cp -R "$ROOT/.claude/skills/$skill" "$RES/engine/skills/"
done
find "$RES/engine" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat >"$BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>ILOVEYELIN2</string>
  <key>CFBundleDisplayName</key><string>ILOVEYELIN2</string>
  <key>CFBundleIdentifier</key><string>com.donghyun.iloveyelin2</string>
  <key>CFBundleExecutable</key><string>ILOVEYELIN2</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$APP_VERSION</string>
  <key>CFBundleVersion</key><string>$BUILD_NUMBER</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSDocumentsFolderUsageDescription</key><string>문서 폴더의 ILOVEYELIN2 폴더에서 논문을 읽고 번역본을 저장합니다.</string>
</dict></plist>
PLIST

find "$BUNDLE" -name .DS_Store -delete
xattr -cr "$BUNDLE"
codesign --force --deep --sign - "$BUNDLE"
codesign --verify --deep "$BUNDLE"

mkdir -p "$DIST"
rm -rf "$DIST/ILOVEYELIN2.app" "$DIST/ILOVEYELIN2.zip"
ditto -c -k --keepParent "$BUNDLE" "$DIST/ILOVEYELIN2.zip"
ditto "$BUNDLE" "$DIST/ILOVEYELIN2.app"
du -sh "$DIST/ILOVEYELIN2.app" "$DIST/ILOVEYELIN2.zip"

#!/bin/bash
# 새 버전을 빌드해 GitHub Releases에 올린다. 설치된 앱은 다음에 켤 때 업데이트를 알려준다.
# 사용: bash app/release.sh 1.2 "바뀐 점 한 줄"
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="funnyhyuny/paper-translation-agent"
VERSION="${1:?버전을 적어 주세요. 예: bash app/release.sh 1.2 \"바뀐 점\"}"
NOTES="${2:-}"
BUILD=$(( $(sed -n 2p "$APP_DIR/VERSION") + 1 ))
TAG="app-v$VERSION"

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "이미 $TAG 릴리스가 있어요. 버전을 올려 주세요." >&2
  exit 1
fi

printf '%s\n%s\n' "$VERSION" "$BUILD" >"$APP_DIR/VERSION"
bash "$APP_DIR/build.sh"

ZIP="$APP_DIR/dist/ILOVEYELIN2.zip"
SHA=$(shasum -a 256 "$ZIP" | cut -d' ' -f1)
URL="https://github.com/$REPO/releases/download/$TAG/ILOVEYELIN2.zip"
VERSION="$VERSION" BUILD="$BUILD" URL="$URL" SHA="$SHA" NOTES="$NOTES" python3 -c '
import json, os
print(json.dumps({"version": os.environ["VERSION"], "build": int(os.environ["BUILD"]), "url": os.environ["URL"],
                  "sha256": os.environ["SHA"], "notes": os.environ["NOTES"]}, ensure_ascii=False, indent=2))
' >"$APP_DIR/dist/version.json"

gh release create "$TAG" "$ZIP" "$APP_DIR/dist/version.json" --repo "$REPO" \
  --title "ILOVEYELIN2 $VERSION" --notes "${NOTES:-ILOVEYELIN2 $VERSION}" --latest
echo "올렸어요: $TAG (build $BUILD)"

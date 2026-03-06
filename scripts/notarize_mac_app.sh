#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_PATH="$DIST_DIR/PaperLocal.app"
VERSION="${VERSION:-}"
NOTARY_PROFILE="${APPLE_NOTARY_PROFILE:-}"
IDENTITY="${APPLE_DEVELOPER_ID_APP:-}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/notarize_mac_app.sh [--app /abs/path/PaperLocal.app] [--version v1.0.1] [--profile PROFILE] [--identity "Developer ID Application: ..."]

Environment variables:
  APPLE_NOTARY_PROFILE    notarytool keychain profile name (required if --profile not set)
  APPLE_DEVELOPER_ID_APP  signing identity (optional; auto-detects first "Developer ID Application" identity)
  VERSION                 release version label (optional; defaults to latest git tag or timestamp)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      APP_PATH="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    --profile)
      NOTARY_PROFILE="$2"
      shift 2
      ;;
    --identity)
      IDENTITY="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$APP_PATH" ]]; then
  echo "Error: app not found at: $APP_PATH"
  echo "Build first with: ./scripts/build_mac_app.sh"
  exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo "Error: xcrun not found. Install Xcode command line tools first."
  exit 1
fi

if [[ -z "$NOTARY_PROFILE" ]]; then
  echo "Error: missing notary profile."
  echo "Set APPLE_NOTARY_PROFILE or pass --profile."
  exit 1
fi

if [[ -z "$IDENTITY" ]]; then
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"\(Developer ID Application:.*\)"/\1/p' | head -n 1)"
fi

if [[ -z "$IDENTITY" ]]; then
  echo "Error: no usable Developer ID Application certificate found."
  echo "Import your certificate to login keychain, or pass --identity explicitly."
  exit 1
fi

if [[ -z "$VERSION" ]]; then
  if git -C "$ROOT_DIR" describe --tags --abbrev=0 >/dev/null 2>&1; then
    VERSION="$(git -C "$ROOT_DIR" describe --tags --abbrev=0)"
  else
    VERSION="$(date +%Y%m%d-%H%M)"
  fi
fi

TMP_ZIP="$DIST_DIR/PaperDesk-${VERSION}-mac-arm64-for-notary.zip"
FINAL_ZIP="$DIST_DIR/PaperDesk-${VERSION}-mac-arm64.zip"
REPORT_JSON="$DIST_DIR/notary-${VERSION}.json"

echo "[1/6] Code sign app"
codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP_PATH"

echo "[2/6] Verify signature"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "[3/6] Create zip for notarization"
rm -f "$TMP_ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$TMP_ZIP"

echo "[4/6] Submit to Apple notarization service"
xcrun notarytool submit "$TMP_ZIP" --keychain-profile "$NOTARY_PROFILE" --wait --output-format json > "$REPORT_JSON"

if command -v jq >/dev/null 2>&1; then
  STATUS="$(jq -r '.status // empty' "$REPORT_JSON")"
  LOG_URL="$(jq -r '.logFileUrl // empty' "$REPORT_JSON")"
else
  STATUS="$(sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPORT_JSON" | head -n 1)"
  LOG_URL="$(sed -n 's/.*"logFileUrl"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPORT_JSON" | head -n 1)"
fi

if [[ "$STATUS" != "Accepted" ]]; then
  echo "Error: notarization failed with status: ${STATUS:-unknown}"
  if [[ -n "$LOG_URL" ]]; then
    echo "Notary log URL: $LOG_URL"
  fi
  echo "Full report: $REPORT_JSON"
  exit 1
fi

echo "[5/6] Staple notarization ticket"
xcrun stapler staple -v "$APP_PATH"
xcrun stapler validate -v "$APP_PATH"

echo "[6/6] Create final distributable zip"
rm -f "$FINAL_ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$FINAL_ZIP"
shasum -a 256 "$FINAL_ZIP"

echo "Done"
echo "Signed & notarized app: $APP_PATH"
echo "Release zip: $FINAL_ZIP"
echo "Notary report: $REPORT_JSON"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm not found. Install Node.js first (e.g. brew install node)."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found."
  exit 1
fi

echo "[1/4] Build frontend dist"
cd "$ROOT_DIR/frontend"
npm install
npm run build

cd "$ROOT_DIR"

echo "[2/4] Prepare build venv"
python3 -m venv .venv-mac-build
source .venv-mac-build/bin/activate

pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r desktop/requirements-mac.txt

echo "[3/4] Build macOS app"
rm -rf build dist
pyinstaller desktop/PaperLocal.spec --noconfirm

echo "[4/4] Done"
echo "App path: $ROOT_DIR/dist/PaperLocal.app"

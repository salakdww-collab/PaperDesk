#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm not found. Install Node.js first (brew install node)."
  exit 1
fi

cd "$ROOT_DIR/frontend"
npm install
npm run build

cd "$ROOT_DIR"
python3 -m venv .venv-desktop
source .venv-desktop/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r desktop/requirements-mac.txt

python desktop/mac_launcher.py

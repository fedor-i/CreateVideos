#!/bin/bash
# One-time setup: Python venv + edge-tts + Playwright Chromium.
# Requires: python3.11+, ffmpeg (brew install ffmpeg).
set -e
cd "$(dirname "$0")"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found — run: brew install ffmpeg"; exit 1; }

PY="${PYTHON:-python3}"
"$PY" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

echo
echo "Done. Activate with:  source .venv/bin/activate"
echo "edge-tts installs a CLI; if cv.synth can't find it, set CV_EDGE_TTS to its path"
echo "(find it with:  which edge-tts )."

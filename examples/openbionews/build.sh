#!/bin/bash
# Reproduce the OpenBioNews two-section video end to end.
# Run from the repo root with the venv active:  examples/openbionews/build.sh
set -e
cd "$(dirname "$0")/../.."          # repo root
EX=examples/openbionews
B=build/openbionews                  # all intermediates live here (gitignored)
mkdir -p "$B/audio"

echo "== 1. narration =="
python -m cv.synth $EX/mcp_script.json      mcp_ "$B/audio"
python -m cv.synth $EX/insights_script.json ins_ "$B/audio"
python -m cv.synth $EX/div_script.json      div_ "$B/audio"

echo "== 2. section 1 — MCP scene (HTML beats) =="
python -m cv.scene $EX/mcp_scene.html "$B/audio/mcp_manifest.json" "$B/sec1_mcp.mp4"

echo "== 3. section 2 — Insights (live site) =="
python -m cv.live $EX/insights_recipe.py "$B/audio/ins_manifest.json" "$B/sec2_insights.mp4"
python -m cv.mux  "$B/timings.json" "$B/audio/ins_manifest.json"      "$B/sec2_insights.mp4"

echo "== 4. cards (render HTML → PNG, then clip) =="
python -c "from cv.cards import render_html_png; \
  render_html_png('$EX/divider.html','$B/open.png','open'); \
  render_html_png('$EX/divider.html','$B/d2.png','d2')"
python -m cv.cards "$B/open.png" "$B/audio/div_open.mp3" "$B/open.mp4"
python -m cv.cards "$B/d2.png"   "$B/audio/div_d2.mp3"   "$B/d2.mp4"

echo "== 5. final cut (trim 2.4s silent head off section 2) =="
python -m cv.assemble "$B/final_obn.mp4" \
  "$B/open.mp4" "$B/sec1_mcp.mp4" "$B/d2.mp4" "2.4~$B/sec2_insights.mp4"

# The shipped OpenBioNews video was voice-only. To add a ducked music bed instead:
if [ "$1" = "--music" ]; then
  echo "== 6. (optional) music bed =="
  python -m cv.music bed "$B/final_obn.mp4" "$B/final_obn_music.mp4"
  echo "DONE → $B/final_obn_music.mp4"
else
  echo "DONE → $B/final_obn.mp4   (add --music for a ducked background track)"
fi

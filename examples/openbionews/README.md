# Example: OpenBioNews — two-feature video

The real build that this pipeline was extracted from. A ~2:20 video in two ~1-minute
sections: **Section 1** explains the MCP server as an HTML scene; **Section 2** records
the live Insights dashboard on the website. Title and section cards bracket them.

Reproduce it (from the repo root, with the venv active):

```bash
./setup.sh && source .venv/bin/activate
examples/openbionews/build.sh
# → build/openbionews/final_obn.mp4
```

## Files

| File | Role | Used by |
|------|------|---------|
| `mcp_script.json` | Section 1 narration (6 beats) | `cv.synth` → `cv.scene` |
| `mcp_scene.html` | Section 1 animation; `show(beat)` toggles `.beat` | `cv.scene` |
| `insights_script.json` | Section 2 narration (7 phases) | `cv.synth` → `cv.mux` |
| `insights_recipe.py` | Section 2 live-site recipe (fill / build / expand / waypoints) | `cv.live` |
| `divider.html` | Title + section-2 cards; `show('open')` / `show('d2')` | `cv.cards` |
| `div_script.json` | Card narration lines | `cv.synth` → `cv.cards` |

## What to copy for a new video

- **A concept/number section** → copy `mcp_scene.html` + `mcp_script.json`. Keep the
  `beat`/`show()` structure; rewrite the beats.
- **A live-product section** → copy `insights_recipe.py` + `insights_script.json`. Change
  `URL`, `PHASES`, and the interactions; keep the off-screen-expand + waypoint pattern.
- **Cards** → copy `divider.html`; it's just styled `.card` divs toggled by `show(id)`.

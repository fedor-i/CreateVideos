# CreateVideos

A small, battle-tested pipeline for producing **narrated 1080p product videos** from
either (a) hand-built HTML "scene" animations or (b) live recordings of a real website —
with voiceover that stays perfectly in sync with what's on screen.

Everything here is free and local: **edge-tts** for narration, **Playwright/Chromium**
for recording, **ffmpeg** for assembly. No paid APIs, no cloud, no accounts.

This grew out of a real job (the OpenBioNews two-feature video) and carries the fixes
that made it stop looking amateurish. See [Hard-won lessons](#hard-won-lessons) — read
those before you touch the recording code.

---

## The mental model

A finished video is a **concatenation of pieces**. Each piece is one of three kinds:

| Kind | Module | What it is | When to use |
|------|--------|------------|-------------|
| **Card** | `cv/cards.py` | A still PNG + a line of narration, with fades | Title, section dividers, outro |
| **Scene** | `cv/scene.py` | A self-contained HTML animation with `beats` | Explaining a concept, a diagram, numbers you control |
| **Live** | `cv/live.py` | A recording of a real website scrolling/clicking | Showing the actual product |

The **narration drives the timing**, never the other way around. You write the script
first; `cv/synth.py` turns each line into an audio clip and measures its exact duration;
the recorders then hold each beat / scroll segment for *that* duration (plus small
breaths). This is why the voice always lands on the right visual.

```
script.json ──▶ synth.py ──▶ *.mp3 + manifest.json (durations)
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                         ▼
     scene.py                   live.py                   cards.py
  (HTML beats)            (real site, eased          (PNG + one line)
          │                 descent + overlay)             │
          └──────────── piece1.mp4 … pieceN.mp4 ───────────┘
                                   │
                              assemble.py
                        (normalize → concat → final.mp4)
```

## Quickstart

```bash
./setup.sh                      # venv + edge-tts + playwright chromium
source .venv/bin/activate

# 1. write a narration script (list of {id, text}) — see examples/
# 2. synthesize voiceover + get durations
python -m cv.synth examples/openbionews/mcp_script.json mcp_ build/audio

# 3a. record a beat-based HTML scene, locked to the narration
python -m cv.scene examples/openbionews/mcp_scene.html build/audio/mcp_manifest.json build/sec1_mcp.mp4

# 3b. …or record a live website (edit the recipe in cv/live.py / pass one)
python -m cv.live examples/openbionews/insights_recipe.py build/audio/ins_manifest.json build/sec2.mp4

# 4. stitch cards + sections into the final 1080p/60fps video
python -m cv.assemble build/final.mp4 \
    build/open.mp4 build/sec1_mcp.mp4 build/sec2.mp4

# 5. (optional) bed ducked background music under the voiceover
python -m cv.music bed build/final.mp4 build/final_music.mp4
```

A complete worked build is in [`examples/openbionews/`](examples/openbionews/) — run
`examples/openbionews/build.sh` to reproduce the real two-section video end to end.

## Requirements

- **Python 3.11+**
- **ffmpeg** with libx264 and the `minterpolate` filter (standard builds have it):
  `brew install ffmpeg`
- Python deps (installed by `setup.sh`): `edge-tts`, `playwright`
- Chromium for Playwright: `playwright install chromium` (setup.sh does this)

## The pieces in detail

### `cv/synth.py` — voiceover
Microsoft Edge neural TTS, offline-free. Default voice `en-US-AndrewNeural` at `-6%`
(a documentary pace). Writes one mp3 per script line and a `*manifest.json` carrying the
measured duration of each — **this is the clock the whole video runs on.**
edge-tts fails transiently, so each line is retried up to 6× with a size check.

Override voice/rate with env vars: `CV_VOICE=en-US-AvaNeural CV_RATE=-3%`.

### `cv/scene.py` — HTML scene animation
Give it a self-contained HTML file exposing a global `show(beatId)` that toggles which
`.beat` is visible. The recorder walks the beats in script order, holding each for its
narration duration (+ a LEAD before the first, a TAIL after the last), then muxes a
locked audio track built from `lead-silence + seg + pad-silence …`. Output 1080p/30fps.
See [`examples/openbionews/mcp_scene.html`](examples/openbionews/mcp_scene.html) for the
shape of a scene.

### `cv/live.py` — live site recording
Records a real page as **one continuous eased descent** (easeInOutSine), narration
overlaid at exact phase offsets, then interpolated to 60fps. You supply a **recipe**: a
small Python module with a `run(page, ctx)` that fills inputs / clicks / expands things,
and returns the scroll **waypoints** to glide through. The OpenBioNews recipe is the
reference. The two non-obvious rules that make it smooth live in
[Hard-won lessons](#hard-won-lessons).

### `cv/cards.py` — title / divider cards
Turns a PNG (render any HTML card to PNG, or use a design tool) + one narration line into
a clip with in/out fades. Used for the opening title and section dividers.

### `cv/assemble.py` — final cut
Normalizes every piece to **1920×1080, 60fps, 48kHz stereo** and concatenates them.
Pieces can be trimmed on the way in (e.g. drop a silent head). Mismatched fps/sample-rate
between pieces is the usual cause of A/V drift at joins — this step exists to kill that.

### `cv/music.py` — optional music bed
A *post* step on a finished (voice-only) video. Synthesizes an upbeat-corporate loop in
ffmpeg — plucky sine arpeggio (I–V–vi–IV) + warm bass + soft kick/hats at ~112 BPM, no
samples, no license — loops it to length, and ducks it under the existing voiceover with
a sidechain compressor so the voice always sits on top. The video stream is **copied**
(`-c:v copy`), so there's no re-encode and no quality loss. Omit this step entirely for a
clean voice-only cut (what the OpenBioNews video shipped as).

```bash
python -m cv.music loop build            # reusable build/music/loop.wav (optional)
python -m cv.music bed in.mp4 out.mp4     # duck music under the VO (auto-makes a loop)
python -m cv.music bed in.mp4 out.mp4 --loop build/music/loop.wav --volume 2.4
```

> **ffmpeg gotcha:** fusing `sidechaincompress` with the video encode in one pass hangs
> at 100% CPU. `cv/music.py` mixes audio first, then remuxes with `-c:v copy`.

## Hard-won lessons

These are not style preferences. Each one fixed a specific, visible defect.

1. **Playwright headless captures ~13fps, not 60.** A raw scroll recording looks janky
   no matter how smooth your easing is. Fix: record at whatever you get, then
   `minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` in post. Motion-
   compensated interpolation is ideal for uniform vertical scroll. Costs ~10–14 min of
   encode on a long clip — worth it. (`cv/mux.py` does this.)

2. **Expand/collapse UI *off-screen*, before the glide — never during.** If you open an
   accordion while it's in view, the layout jumps and the scroll position lurches. Scroll
   to top, set every `<details>` to its final open/closed state, wait for re-render, *then*
   measure waypoints and start the single continuous descent.

3. **One continuous eased scroll beats many small scrolls.** Compute all waypoints up
   front, then glide between them with easeInOutSine. Stop-start scrolling reads as
   "a robot is driving this."

4. **`device_scale_factor=1`, not 2.** DSF=2 doubles the pixels the screencast has to
   ship and *lowers* the effective frame rate — the opposite of what you want.

5. **The voice is the clock.** Synthesize first, measure durations, then hold visuals to
   match. Don't guess timings and hope the VO fits.

6. **edge-tts is flaky.** Retry each line (6× here) and assert the mp3 is > ~1.5 KB; it
   happily writes empty files on failure.

7. **Normalize before you concat.** Different fps or sample rates across pieces drift at
   the joins. `assemble.py` forces every piece to the same spec first.

8. **A short musical rest at each join is fine.** Voice-only (no music bed) leaves ~3–4s
   of quiet at card transitions. That reads as a breath, not a bug. Add a music bed if you
   want it filled.

## Layout

```
CreateVideos/
├── README.md
├── setup.sh                 # venv + deps + chromium
├── requirements.txt
├── cv/                      # the pipeline
│   ├── synth.py             # narration → mp3 + durations
│   ├── scene.py             # HTML beats → video
│   ├── live.py              # live site → eased recording
│   ├── mux.py               # overlay narration + interpolate to 60fps
│   ├── cards.py             # PNG + line → card clip
│   ├── assemble.py          # normalize + concat → final
│   └── music.py             # optional: synth loop + duck under the VO
└── examples/
    └── openbionews/         # the real two-section build, reproducible
```

## License

Personal tooling. Use freely.

#!/usr/bin/env python3
"""Synthesize per-line narration with edge-tts and record each line's exact duration.

The manifest this writes is the clock the whole video runs on: every recorder holds
its visuals to the durations measured here.

Usage:
    python -m cv.synth <script.json> <prefix> <outdir>

script.json is a list of {"id": "01", "text": "...", "beat"?: "b1"} objects.
Env overrides:  CV_VOICE (default en-US-AndrewNeural), CV_RATE (default -6%),
                CV_EDGE_TTS (path to the edge-tts binary).
"""
import json
import os
import subprocess
import sys
import time

VOICE = os.environ.get("CV_VOICE", "en-US-AndrewNeural")
RATE = os.environ.get("CV_RATE", "-6%")  # a touch slower → documentary pace
EDGE = os.environ.get("CV_EDGE_TTS", os.path.expanduser("~/.local/bin/edge-tts"))
RETRIES = 6
MIN_BYTES = 1500  # edge-tts writes tiny/empty files on failure


def dur(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        text=True).strip()
    return float(out)


def synth_line(text, mp3):
    """Synthesize one line with retries; edge-tts fails transiently."""
    edge = EDGE if os.path.exists(EDGE) else "edge-tts"  # fall back to PATH
    for _ in range(RETRIES):
        r = subprocess.run(
            [edge, "--voice", VOICE, f"--rate={RATE}", "--text", text,
             "--write-media", mp3],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0 and os.path.exists(mp3) and os.path.getsize(mp3) > MIN_BYTES:
            return
        time.sleep(2.0)
    raise RuntimeError(f"edge-tts failed to synthesize: {text[:60]!r}")


def main(script_json, prefix, outdir):
    segs = json.load(open(script_json))
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for s in segs:
        mp3 = os.path.join(outdir, f"{prefix}{s['id']}.mp3")
        synth_line(s["text"], mp3)
        d = dur(mp3)
        manifest.append({
            "id": s["id"],
            "beat": s.get("beat", s["id"]),
            "phase": s.get("phase", s["id"]),
            "mp3": mp3,
            "dur": round(d, 3),
            "text": s["text"],
        })
        print(f"{s['id']:>4}  {d:6.2f}s  {s['text'][:60]}")
    manifest_path = os.path.join(outdir, f"{prefix}manifest.json")
    json.dump(manifest, open(manifest_path, "w"), indent=2)
    print("TOTAL", round(sum(m["dur"] for m in manifest), 2), "s  →", manifest_path)
    return manifest_path


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

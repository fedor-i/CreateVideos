#!/usr/bin/env python3
"""Record a beat-based HTML scene locked to its narration, then mux A/V.

The scene HTML must expose a global `show(beatId)` that toggles which `.beat` is
visible. This walks the beats in manifest order, holding each for its narration
duration (+ LEAD before the first, + TAIL after the last), builds a matching locked
audio track, and muxes to 1080p/30fps.

Usage:
    python -m cv.scene <scene.html> <manifest.json> <out.mp4> [LEAD] [PAD] [TAIL]
"""
import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright


def _sil(t, path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{t}", "-ar", "48000", "-ac", "2", path],
                   check=True, capture_output=True)


def _towav(src, path):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "48000", "-ac", "2", path],
                   check=True, capture_output=True)


def _probe(path):
    return subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path], text=True).strip()


def main(scene_html, manifest_json, out, lead=1.0, pad=0.55, tail=1.4):
    scene = os.path.abspath(scene_html)
    manifest = json.load(open(manifest_json))
    out = os.path.abspath(out)
    work = os.path.dirname(out)
    clips = os.path.join(work, "clips")
    aud = os.path.join(work, "audio")
    os.makedirs(clips, exist_ok=True)
    os.makedirs(aud, exist_ok=True)

    # 1. hold each beat for its narration duration (+ LEAD first, + TAIL last)
    holds = []
    for i, m in enumerate(manifest):
        h = m["dur"] + pad + (lead if i == 0 else 0) + (tail if i == len(manifest) - 1 else 0)
        holds.append((m["beat"], h))

    rec_dir = os.path.join(clips, "rec")
    os.makedirs(rec_dir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080},
                            record_video_dir=rec_dir,
                            record_video_size={"width": 1920, "height": 1080},
                            device_scale_factor=1)
        pg = ctx.new_page()
        pg.goto("file://" + scene)
        pg.wait_for_timeout(300)
        pg.evaluate(f"show('{manifest[0]['beat']}')")
        for beat, h in holds:
            pg.evaluate(f"show('{beat}')")
            pg.wait_for_timeout(int(h * 1000))
        ctx.close()
        b.close()
        webm = pg.video.path()
    print("recorded:", webm)

    # 2. locked audio: lead-silence + (seg + pad-silence) per line, tail on the last
    pieces = []
    lead_wav = os.path.join(aud, "_lead.wav")
    _sil(lead, lead_wav)
    pieces.append(lead_wav)
    for i, m in enumerate(manifest):
        w = os.path.join(aud, f"_seg{i}.wav")
        _towav(m["mp3"], w)
        pieces.append(w)
        padt = pad + (tail if i == len(manifest) - 1 else 0)
        ps = os.path.join(aud, f"_pad{i}.wav")
        _sil(padt, ps)
        pieces.append(ps)

    concat_list = os.path.join(aud, "_concat.txt")
    open(concat_list, "w").write("".join(f"file '{p}'\n" for p in pieces))
    full = os.path.join(aud, "_full.wav")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                    "-c", "copy", full], check=True, capture_output=True)
    print("audio dur:", _probe(full))

    # 3. mux: normalize video to 30fps 1080p, clone-pad the tail, trim to audio
    subprocess.run(
        ["ffmpeg", "-y", "-i", webm, "-i", full, "-filter_complex",
         "[0:v]fps=30,scale=1920:1080:flags=lanczos,format=yuv420p,"
         "tpad=stop_mode=clone:stop_duration=3[v]",
         "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
        check=True)
    print("WROTE", out, _probe(out) + "s")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    a = sys.argv
    main(a[1], a[2], a[3],
         float(a[4]) if len(a) > 4 else 1.0,
         float(a[5]) if len(a) > 5 else 0.55,
         float(a[6]) if len(a) > 6 else 1.4)

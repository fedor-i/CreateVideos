#!/usr/bin/env python3
"""Build a title / divider card clip from a still PNG + one line of narration.

The clip is 1920x1080/60fps: the PNG held for (0.6 + narration + 1.1)s with a fade in
and out, the voiceover delayed 0.6s so it lands after the fade-in.

Render the PNG however you like — a quick way is to screenshot an HTML card (see
`render_html_png` below), or export from any design tool.

Usage:
    python -m cv.cards <card.png> <voiceover.mp3> <out.mp4>
"""
import os
import subprocess
import sys


def _dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", p], text=True).strip())


def render_html_png(html_path, png_path, show_id=None):
    """Optional helper: screenshot a 1920x1080 HTML card to PNG via Playwright.

    If `show_id` is given, calls the page's global `show(id)` first (for multi-card files).
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])
        pg = b.new_context(viewport={"width": 1920, "height": 1080},
                           device_scale_factor=1).new_page()
        pg.goto("file://" + os.path.abspath(html_path))
        pg.wait_for_timeout(300)
        if show_id:
            pg.evaluate(f"show('{show_id}')")
            pg.wait_for_timeout(200)
        pg.screenshot(path=png_path)
        b.close()
    return png_path


def main(png, vo, out):
    out = os.path.abspath(out)
    vd = _dur(vo)
    total = round(0.6 + vd + 1.1, 3)
    fade_out = round(total - 0.5, 3)
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", png, "-i", vo, "-filter_complex",
         f"[0:v]scale=1920:1080,fps=60,format=yuv420p,"
         f"fade=t=in:st=0:d=0.4,fade=t=out:st={fade_out}:d=0.5[v];"
         f"[1:a]adelay=600|600,aresample=48000,apad,atrim=0:{total}[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{total}",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
        check=True)
    print("made", out, f"({total}s)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

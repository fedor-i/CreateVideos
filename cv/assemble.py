#!/usr/bin/env python3
"""Normalize every piece to 1920x1080 / 60fps / 48kHz stereo and concatenate them.

Mismatched fps or sample rates across pieces drift at the joins; normalizing first kills
that. Any piece may be trimmed on the way in with a leading `START~` (seconds), e.g. to
drop a silent head: `START2.4~build/sec2.mp4`.

Usage:
    python -m cv.assemble <out.mp4> piece1.mp4 [START2.4~]piece2.mp4 ...
"""
import os
import subprocess
import sys


def _parse(piece):
    """'2.4~path.mp4' -> (2.4, 'path.mp4');  'path.mp4' -> (None, 'path.mp4')."""
    if "~" in piece:
        head, path = piece.split("~", 1)
        try:
            return float(head), path
        except ValueError:
            return None, piece
    return None, piece


def main(out, pieces):
    out = os.path.abspath(out)
    inputs = []
    for start, path in (_parse(p) for p in pieces):
        if start is not None:
            inputs += ["-ss", f"{start}"]
        inputs += ["-i", os.path.abspath(path)]

    n = len(pieces)
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale=1920:1080,fps=60,setsar=1,format=yuv420p[v{i}]")
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{concat_in}concat=n={n}:v=1:a=1[v][a]")
    fc = ";".join(parts)

    subprocess.run(["ffmpeg", "-y"] + inputs +
                   ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
                   check=True)
    dur = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", out], text=True).strip()
    print("FINAL", out, f"{dur}s")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2:])

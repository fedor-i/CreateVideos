#!/usr/bin/env python3
"""Overlay narration onto a live recording at exact phase offsets, interpolate to 60fps, mux.

Reads a `timings.json` (written by cv.live) describing the recorded webm and how long
each narration phase was held, plus the synth manifest (phase -> mp3). Places each
narration clip at its phase's start offset over a silent base the length of the video,
then motion-interpolates the (low-fps) screencast up to a smooth 60fps.

Usage:
    python -m cv.mux <timings.json> <manifest.json> <out.mp4>
"""
import json
import os
import subprocess
import sys


def _vdur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", p], text=True).strip())


def main(timings_json, manifest_json, out):
    info = json.load(open(timings_json))
    man = json.load(open(manifest_json))
    # manifest carries a "phase" per clip (falls back to id in cv.synth)
    mp3_by_phase = {m.get("phase", m["id"]): m["mp3"] for m in man}

    webm = info["webm"]
    lead = info["LEAD"]
    holds = info["timings"]
    wd = _vdur(webm)
    sum_h = sum(h["hold"] for h in holds)
    pre = max(0.0, wd - sum_h)  # the recorder's build/settle head, before narration starts
    print(f"webm={wd:.2f} holds={sum_h:.2f} pre_roll={pre:.2f}")

    starts = []
    cum = pre
    for i, h in enumerate(holds):
        starts.append((h["phase"], cum + (lead if i == 0 else 0.0)))
        cum += h["hold"]
    for p, s in starts:
        print(f"  {p:9} @ {s:6.2f}s")

    # input 0 = webm (video); input 1 = silent base (full length); inputs 2+ = narration
    inputs = ["-f", "lavfi", "-t", f"{wd:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    fc = []
    mix = ["[1:a]"]
    for idx, (p, s) in enumerate(starts, start=2):
        inputs += ["-i", mp3_by_phase[p]]
        ms = int(s * 1000)
        fc.append(f"[{idx}:a]aresample=48000,adelay={ms}|{ms}[a{idx}]")
        mix.append(f"[a{idx}]")
    fc.append("".join(mix) + f"amix=inputs={len(starts)+1}:normalize=0:duration=first,"
              f"atrim=0:{wd:.3f},alimiter=limit=0.95[aout]")

    fo = max(0.0, wd - 0.7)
    vf = (f"[0:v]scale=1920:1080:flags=lanczos,"
          f"minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
          f"format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st={fo:.2f}:d=0.7[v]")

    out = os.path.abspath(out)
    subprocess.run(["ffmpeg", "-y", "-i", webm] + inputs +
                   ["-filter_complex", f"{vf};{';'.join(fc)}",
                    "-map", "[v]", "-map", "[aout]",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", out],
                   check=True)
    print("WROTE", out, f"{_vdur(out):.2f}s")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

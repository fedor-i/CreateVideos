#!/usr/bin/env python3
"""Optional music bed: generate an upbeat-corporate loop, duck it under the voiceover.

This is a *post* step. Run it on a finished video that already has a narration track
(e.g. the output of `cv.assemble`): it loops a music bed to the video's length, ducks it
under the existing voice with a sidechain compressor, and remuxes — copying the video
stream untouched, so no re-encode and no quality loss.

The loop is synthesized in ffmpeg (no samples, no license): a plucky sine arpeggio
(I-V-vi-IV in C) + warm bass + soft kick/hats at ~112 BPM. Reuse one loop across videos.

Usage:
    python -m cv.music loop <outdir>                      # writes <outdir>/music/loop.wav
    python -m cv.music bed  <in.mp4> <out.mp4> [options]  # add ducked music under the VO
        options:  --loop <loop.wav>   reuse an existing loop (else one is generated)
                  --volume <N>        music loudness before ducking (default 2.4)

Gotcha (why this is a separate pass): fusing sidechaincompress with the video encode in
one ffmpeg run hangs at 100% CPU. We mix audio first, then remux with `-c:v copy`.
"""
import os
import subprocess
import sys
import tempfile

FF = os.environ.get("FFMPEG", "ffmpeg")


def _run(a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", p], text=True).strip())


# --- music loop synthesis (ported from the demo-video skill) ---------------------------

def make_loop(outdir):
    """Synthesize a ~8.6s loopable music bed → <outdir>/music/loop.wav."""
    OUT = os.path.join(outdir, "music")
    os.makedirs(OUT, exist_ok=True)
    BPM = 112
    beat = 60.0 / BPM
    bar = 4 * beat
    eighth = beat / 2
    loop_len = 4 * bar
    cache = {}

    def synth(kind, f=0):
        key = (kind, round(f, 2))
        if key in cache:
            return cache[key]
        p = os.path.join(OUT, f"_{kind}_{int(f)}.wav")
        if kind == "pluck":
            _run([FF, "-y", "-f", "lavfi", "-i",
                  f"sine=frequency={f}:duration=0.5:sample_rate=44100",
                  "-af", "afade=t=in:d=0.004,afade=t=out:st=0.04:d=0.45:curve=exp,lowpass=f=3800",
                  "-ac", "2", p])
        elif kind == "bass":
            _run([FF, "-y", "-f", "lavfi", "-i",
                  f"sine=frequency={f}:duration=1.9:sample_rate=44100",
                  "-af", "afade=t=in:d=0.01,afade=t=out:st=1.0:d=0.9,lowpass=f=600", "-ac", "2", p])
        elif kind == "kick":
            _run([FF, "-y", "-f", "lavfi", "-i", "sine=frequency=62:duration=0.2:sample_rate=44100",
                  "-af", "afade=t=out:st=0:d=0.2:curve=exp,lowpass=f=200", "-ac", "2", p])
        elif kind == "hat":
            _run([FF, "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.06:c=pink:a=0.6:r=44100",
                  "-af", "highpass=f=7500,afade=t=out:st=0:d=0.06:curve=exp", "-ac", "2", p])
        cache[key] = p
        return p

    CH = [dict(arp=[261.63, 329.63, 392.00, 523.25], bass=65.41),   # C
          dict(arp=[196.00, 246.94, 293.66, 392.00], bass=98.00),   # G
          dict(arp=[220.00, 261.63, 329.63, 440.00], bass=110.00),  # Am
          dict(arp=[174.61, 220.00, 261.63, 349.23], bass=87.31)]   # F
    PAT = [0, 1, 2, 3, 2, 1, 0, 1]
    events = []
    for b, ch in enumerate(CH):
        t0 = b * bar
        events.append((synth("bass", ch["bass"]), t0, 0.55))
        for j, idx in enumerate(PAT):
            events.append((synth("pluck", ch["arp"][idx]), t0 + j * eighth, 0.42))
        for kb in (0, 2):
            events.append((synth("kick"), t0 + kb * beat, 0.85))
        for j in (1, 3, 5, 7):
            events.append((synth("hat"), t0 + j * eighth, 0.22))

    inp, filt, lab = [], [], []
    for i, (wav, t, g) in enumerate(events):
        inp += ["-i", wav]
        filt.append(f"[{i}]adelay={int(t*1000)}:all=1,volume={g}[e{i}]")
        lab.append(f"[e{i}]")
    loop = os.path.join(OUT, "loop.wav")
    _run([FF, "-y", *inp, "-filter_complex",
          ";".join(filt) + ";" + "".join(lab) +
          f"amix=inputs={len(events)}:normalize=0,atrim=0:{loop_len:.3f}[m]",
          "-map", "[m]", "-ac", "2", "-ar", "44100", loop])
    for f in cache.values():
        try:
            os.remove(f)
        except OSError:
            pass
    print("wrote", loop)
    return loop


# --- bed the loop under an existing voiceover -------------------------------------------

def add_bed(in_mp4, out_mp4, loop=None, volume=2.4):
    """Duck `loop` under in_mp4's existing audio and remux (video stream copied)."""
    in_mp4 = os.path.abspath(in_mp4)
    out_mp4 = os.path.abspath(out_mp4)
    total = _dur(in_mp4)
    tmp = tempfile.mkdtemp(prefix="cv_music_")
    if loop is None:
        loop = make_loop(tmp)
    reps = int(total / _dur(loop)) + 2

    # 1. looped, faded music bed to full length
    bed = os.path.join(tmp, "_bed.wav")
    _run([FF, "-y", "-stream_loop", str(reps), "-i", loop, "-t", f"{total:.3f}", "-af",
          f"aecho=0.9:0.9:45:0.18,volume={volume},alimiter=limit=0.9,"
          f"afade=t=in:st=0:d=1.2,afade=t=out:st={total-1.6:.2f}:d=1.6",
          "-ac", "2", "-ar", "44100", bed])

    # 2. sidechain-duck bed under the VO, mix — audio-only pass (fusing with video hangs)
    mix = os.path.join(tmp, "_mix.wav")
    _run([FF, "-y", "-i", in_mp4, "-i", bed, "-filter_complex",
          "[1:a][0:a]sidechaincompress=threshold=0.05:ratio=5:attack=15:release=280[duck];"
          f"[0:a][duck]amix=inputs=2:normalize=0,atrim=0:{total:.3f},"
          "aformat=channel_layouts=stereo[m]",
          "-map", "[m]", "-ar", "44100", "-ac", "2", mix])

    # 3. remux: original video (copied) + new mixed audio
    _run([FF, "-y", "-i", in_mp4, "-i", mix, "-map", "0:v:0", "-map", "1:a:0",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_mp4])
    print("WROTE", out_mp4, f"{_dur(out_mp4):.2f}s")
    return out_mp4


def main(argv):
    if len(argv) >= 2 and argv[0] == "loop":
        make_loop(argv[1])
        return
    if len(argv) >= 3 and argv[0] == "bed":
        in_mp4, out_mp4 = argv[1], argv[2]
        loop, volume = None, 2.4
        rest = argv[3:]
        i = 0
        while i < len(rest):
            if rest[i] == "--loop":
                loop = rest[i + 1]
                i += 2
            elif rest[i] == "--volume":
                volume = float(rest[i + 1])
                i += 2
            else:
                i += 1
        add_bed(in_mp4, out_mp4, loop, volume)
        return
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

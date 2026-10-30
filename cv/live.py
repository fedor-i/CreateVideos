#!/usr/bin/env python3
"""Record a LIVE website as one smooth, continuous eased descent, narration-locked.

You supply a *recipe* (a Python file exporting `RECIPE`, an instance of a class with the
interface below). The recorder walks the phases named in your narration script, calling
the recipe to perform interactions (fill, click, expand) and to tell it where to scroll.
It writes the raw webm plus a `timings.json`; feed both (with the synth manifest) to
`cv.mux` to overlay the voiceover and interpolate to a smooth 60fps.

Recipe interface:
    class MyRecipe:
        URL = "https://..."
        PHASES = ["intro", "controls", "build", "stats", ...]   # must match script "phase"s
        def setup(self, page, H): ...        # after load, before timing starts (optional)
        def phase(self, page, H, name):
            # do interactions for this phase; return {} or:
            #   {"target_y": <int>}    → glide there over the phase's narration duration
            #   {"min_hold": <float>}  → ensure the phase lasts at least this long (e.g. a load)
            ...

See examples/openbionews/insights_recipe.py for the reference recipe.

Usage:
    python -m cv.live <recipe.py> <manifest.json> <out.mp4>
"""
import importlib.util
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

LEAD, PAD, TAIL = 1.0, 0.5, 1.4


class Helpers:
    """Scroll + accordion helpers passed to recipes. See hard-won lessons in the README."""

    def __init__(self, page):
        self.page = page

    def glide(self, to_y, ms):
        """Blocking easeInOutSine scroll to `to_y` over `ms` milliseconds."""
        self.page.evaluate("""([toY,ms])=>new Promise(res=>{
            const el=document.scrollingElement||document.documentElement;
            const sY=el.scrollTop, dY=toY-sY, t0=performance.now();
            if(ms<=0){el.scrollTop=toY;return res();}
            function step(t){ let k=Math.min(1,(t-t0)/ms);
              const e=-(Math.cos(Math.PI*k)-1)/2;
              el.scrollTop=sY+dY*e; if(k<1)requestAnimationFrame(step); else res(); }
            requestAnimationFrame(step); })""", [to_y, ms])

    def scroll_top(self):
        self.page.evaluate("(document.scrollingElement||document.documentElement).scrollTop=0")

    def abs_y(self, text):
        """Absolute document Y of the first element containing `text`."""
        box = self.page.get_by_text(text).first.bounding_box()
        top = self.page.evaluate("(document.scrollingElement||document.documentElement).scrollTop")
        return (top + box["y"]) if box else top

    def collapse_all(self):
        self.page.evaluate("()=>document.querySelectorAll('details').forEach(d=>d.open=false)")

    def set_drawer(self, name, open_):
        """Open/close the <details> whose <summary> starts with `name`."""
        self.page.evaluate("""([n,o])=>{const d=[...document.querySelectorAll('details')]
          .find(x=>(((x.querySelector('summary')||{}).innerText)||'').trim().startsWith(n));
          if(d)d.open=o;}""", [name, open_])

    def full_height(self):
        return self.page.evaluate("(document.scrollingElement||document.documentElement).scrollHeight")

    def clamp(self, y, vh=1080):
        full = self.full_height()
        return max(0, min(full - vh, int(y)))


def load_recipe(path):
    spec = importlib.util.spec_from_file_location("cv_recipe", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RECIPE


def main(recipe_path, manifest_json, out, lead=LEAD, pad=PAD, tail=TAIL):
    recipe = load_recipe(recipe_path)
    man = json.load(open(manifest_json))
    dur_by_phase = {m.get("phase", m["id"]): m["dur"] for m in man}
    phases = recipe.PHASES
    out = os.path.abspath(out)
    work = os.path.dirname(out)
    rec_dir = os.path.join(work, "clips", "rec_live")
    os.makedirs(rec_dir, exist_ok=True)

    timings = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080},
                            device_scale_factor=1,  # DSF=1 → higher effective capture fps
                            record_video_dir=rec_dir,
                            record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page()
        pg.goto(recipe.URL, wait_until="domcontentloaded")
        pg.add_style_tag(content="*{scroll-behavior:auto !important}")
        pg.wait_for_timeout(1500)
        H = Helpers(pg)
        if hasattr(recipe, "setup"):
            recipe.setup(pg, H)

        last = len(phases) - 1
        for i, name in enumerate(phases):
            base = dur_by_phase[name] + pad + (lead if i == 0 else 0) + (tail if i == last else 0)
            t0 = time.time()
            res = recipe.phase(pg, H, name) or {}
            hold = max(base, res.get("min_hold", 0.0))
            target = res.get("target_y")
            if target is not None:
                remaining = max(0.0, hold - (time.time() - t0))
                H.glide(int(target), int(remaining * 1000))
            time.sleep(max(0.0, hold - (time.time() - t0)))
            timings.append({"phase": name, "hold": round(hold, 3)})

        ctx.close()
        b.close()
        webm = pg.video.path()

    timings_json = os.path.join(work, "timings.json")
    json.dump({"webm": str(webm), "timings": timings, "LEAD": lead, "PAD": pad, "TAIL": tail},
              open(timings_json, "w"), indent=2)
    print("WEBM", webm)
    print("TIMINGS", json.dumps(timings))
    print("→", timings_json, "   now run:  python -m cv.mux", timings_json, manifest_json, out)
    return timings_json


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])

"""Reference recipe for cv.live — records the live OpenBioNews Insights dashboard.

Demonstrates the two rules that make a live recording look professional (see README):
  - expand/collapse accordions OFF-SCREEN during the `build` phase, before any scrolling;
  - measure all scroll waypoints up front, then glide between them continuously.

Phases here must match the "phase" fields in insights_script.json.
"""
import time


class InsightsRecipe:
    URL = "https://fedor-i.github.io/OpenBioNews/?tab=insights"
    PHASES = ["intro", "controls", "build", "stats", "methods", "drawers", "close"]

    def __init__(self):
        self.w_stats = 240
        self.w_methods = 520
        self.w_patterns = 1200

    def setup(self, page, H):
        try:
            page.get_by_role("tab", name="Insights").click(timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(800)

    def phase(self, page, H, name):
        if name == "intro":
            return {}  # static hold while the dashboard sits idle

        if name == "controls":
            try:
                box = page.get_by_placeholder("Defaults to your watchlist")
                box.click()
                box.fill("GLP-1")
            except Exception as e:
                print("subject:", e)
            page.wait_for_timeout(400)
            try:  # switch to Research mode
                sel = page.locator("select")
                for i in range(sel.count()):
                    opts = sel.nth(i).locator("option").all_inner_texts()
                    if any("Research" in o for o in opts):
                        sel.nth(i).select_option(value="research")
                        break
            except Exception as e:
                print("mode:", e)
            return {}

        if name == "build":
            t0 = time.time()
            try:
                page.get_by_role("button", name="Build digest").click()
            except Exception as e:
                print("build:", e)
            for _ in range(40):  # wait for the digest to render
                try:
                    if page.get_by_text("developments").first.is_visible():
                        break
                except Exception:
                    pass
                page.wait_for_timeout(500)
            page.wait_for_timeout(3800)       # let the live digest settle fully
            # --- expand OFF-SCREEN, then measure waypoints (rules 2 & 3) ---
            H.scroll_top()
            H.collapse_all()
            H.set_drawer("Trials halted", True)
            H.set_drawer("Patterns & analysis", True)
            page.wait_for_timeout(1100)
            try:
                self.w_stats = H.clamp(H.abs_y("Momentum") - 560)
            except Exception:
                pass
            try:
                self.w_methods = H.clamp(H.abs_y("Methods:") - 560)
            except Exception:
                pass
            try:
                self.w_patterns = H.clamp(H.abs_y("Patterns & analysis") - 140)
            except Exception:
                pass
            return {"min_hold": (time.time() - t0) + 0.4}

        if name == "stats":
            return {"target_y": self.w_stats}
        if name == "methods":
            return {"target_y": self.w_methods}
        if name == "drawers":
            return {"target_y": self.w_patterns}
        if name == "close":
            return {"target_y": H.clamp(self.w_patterns + 150)}
        return {}


RECIPE = InsightsRecipe()

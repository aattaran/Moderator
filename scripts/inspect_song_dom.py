"""Step 2 prep — load a real song page in headless Chromium and dump the
selectors my recorder will need.

This is throwaway diagnostic — verifies:
  1. URL shape /v/<videoId>/<styleHash> renders the song page
  2. Cover-art (img element) is present after load
  3. The "Start recording" button (or whatever today's modal-to-inline
     refactor named it) exists, and what its selector looks like
  4. The button's disabled state behavior — is it disabled until artwork
     is ready, then enabled?

Output:
  - data/dom_inspection/page-initial.png    (screenshot at first paint)
  - data/dom_inspection/page-ready.png      (after waiting for network idle)
  - stdout: the relevant DOM excerpts and selector candidates
"""

import asyncio
import json
import sys
from pathlib import Path

# Windows console default cp1252 chokes on glyphs like U+25B6 in button labels.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

URL = "https://comments-song.app/v/ft_b619a68e0cc6e890/929260ad9b9ea9fe"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "dom_inspection"


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        # Match the device pixel ratio + viewport that the inline ShortsSection
        # is likely tuned for. Default desktop viewport is fine for inspection.
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        print(f">>> navigating to {URL}")
        try:
            resp = await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"FAIL navigate: {e}")
            await browser.close()
            return 1
        print(f"    HTTP {resp.status if resp else '?'}, title={await page.title()!r}")
        await page.screenshot(path=str(OUT_DIR / "page-initial.png"), full_page=True)

        print(">>> waiting for networkidle (max 30s)")
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print(f"    note: networkidle did not arrive ({e}) — continuing")
        await page.screenshot(path=str(OUT_DIR / "page-ready.png"), full_page=True)

        # --- Locate audio + artwork + recording controls ---
        print("\n>>> probing for audio element")
        audio = await page.query_selector("audio")
        if audio:
            src = await audio.get_attribute("src")
            print(f"    audio[src] present: src starts with {(src or '')[:80]!r}")
        else:
            print("    no <audio> element on page")

        print("\n>>> probing for artwork <img>")
        # The shorts canvas needs the artwork to render; the live page also
        # shows it as a normal <img>. Either form tells us cover-art arrived.
        imgs = await page.query_selector_all("img")
        print(f"    found {len(imgs)} <img> elements")
        for i, img in enumerate(imgs[:6]):
            src = await img.get_attribute("src")
            alt = await img.get_attribute("alt")
            crossorigin = await img.get_attribute("crossorigin")
            print(f"    [{i}] alt={alt!r} src={(src or '')[:90]!r} crossorigin={crossorigin!r}")

        # --- Find the recording button by multiple candidate selectors ---
        print("\n>>> probing for 'Start recording' button (multiple candidate selectors)")
        candidates = [
            "button:has-text('Start recording')",
            "button:has-text('Record')",
            "button:has-text('Export')",
            "button:has-text('Download')",
            "[data-testid*='record']",
            "[data-testid*='shorts']",
            "[aria-label*='record' i]",
            "[aria-label*='shorts' i]",
        ]
        for sel in candidates:
            try:
                el = await page.query_selector(sel)
            except Exception as e:
                print(f"    [{sel!r}] error: {e}")
                continue
            if el:
                text = (await el.text_content() or "").strip()
                disabled = await el.get_attribute("disabled")
                aria_disabled = await el.get_attribute("aria-disabled")
                print(
                    f"    [HIT] {sel!r}  text={text!r}  "
                    f"disabled={disabled!r}  aria-disabled={aria_disabled!r}"
                )

        # --- Dump every <button> on page for reference ---
        print("\n>>> dumping all <button> elements (text, disabled, aria-label)")
        buttons = await page.query_selector_all("button")
        print(f"    {len(buttons)} buttons total")
        for i, b in enumerate(buttons):
            text = (await b.text_content() or "").strip().replace("\n", " ")[:60]
            disabled = await b.get_attribute("disabled")
            aria = await b.get_attribute("aria-label")
            tid = await b.get_attribute("data-testid")
            print(
                f"    [{i:2d}] text={text!r:<35}  disabled={disabled!r:<6}  "
                f"aria={aria!r}  data-testid={tid!r}"
            )

        # --- Probe canvas elements (artwork may be rendered as <canvas>) ---
        print("\n>>> probing for <canvas> elements (likely the shorts compositor)")
        canvases = await page.query_selector_all("canvas")
        print(f"    found {len(canvases)} <canvas> elements")
        for i, c in enumerate(canvases):
            w = await c.get_attribute("width")
            h = await c.get_attribute("height")
            cls = await c.get_attribute("class")
            print(f"    [{i}] width={w!r} height={h!r} class={cls!r}")

        # --- Probe inline style for background-image (artwork could be there) ---
        print("\n>>> probing for elements with background-image style")
        bg_elements = await page.eval_on_selector_all(
            "[style*='background-image']",
            "els => els.slice(0, 8).map(e => ({tag: e.tagName, cls: e.className, style: e.getAttribute('style').slice(0, 200)}))",
        )
        for el in bg_elements:
            print(f"    {el}")

        # --- Probe the shorts section heading / region ---
        print("\n>>> probing for any heading mentioning 'shorts'")
        for tag in ("h1", "h2", "h3", "h4", "section"):
            elements = await page.query_selector_all(tag)
            for el in elements:
                t = (await el.text_content() or "").strip()
                if "short" in t.lower() and len(t) < 120:
                    print(f"    <{tag}> text={t!r}")

        # --- Save HTML excerpt around the recording region ---
        print("\n>>> saving full page HTML for offline inspection")
        html = await page.content()
        (OUT_DIR / "page.html").write_text(html, encoding="utf-8")
        print(f"    wrote {OUT_DIR / 'page.html'} ({len(html)} bytes)")

        await browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

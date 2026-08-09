"""Convention #7 — open the prod song page in headless Chromium, screenshot,
verify audio + lyrics + new ShortsPlayer surface render correctly.

Uses a fresh prompt that just submitted (no auto-render → shorts_video_status
will be NULL → ShortsPlayer should show 'Shorts video coming soon').

If you want to re-use an existing song, pass --video-id and --style-hash.
"""

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "prod_songpage_smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Use one of the songs from earlier smokes — they have status=done +
# artwork. shorts_video_status will be 'rendering' or 'failed' (set
# pre-Option-A-deploy) but the UI should still render the audio + lyrics.
# After Option A ships, shortsVideoStatus on these existing rows is
# 'rendering' (some) or 'failed' (some). For NEW songs going forward
# it'll be NULL and the new "coming soon" branch fires. Both code paths
# are valid for the deploy verification.
SONG_URL = "https://comments-song.app/v/ft_815481e113e0c265/929260ad9b9ea9fe"


async def main() -> int:
    from playwright.async_api import async_playwright

    print(f"\n[1] navigate {SONG_URL}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await ctx.new_page()
        try:
            resp = await page.goto(SONG_URL, wait_until="domcontentloaded", timeout=30_000)
            print(f"    HTTP {resp.status if resp else '?'}, title={await page.title()!r}")
        except Exception as e:
            print(f"    FAIL navigate: {e}")
            await browser.close()
            return 1

        # Wait for any client-side hydration + skeleton settling.
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        screenshot = OUT_DIR / "prod_song_page.png"
        await page.screenshot(path=str(screenshot), full_page=True)
        print(f"    screenshot: {screenshot}")

        print("\n[2] DOM probes — does the Option A surface render?")
        # AudioPlayer should exist (the canonical audio surface).
        audio = await page.query_selector("audio")
        print(f"    <audio>: {'present' if audio else 'MISSING'}")
        if audio:
            audio_src = await audio.get_attribute("src")
            print(f"    audio src: {audio_src[:90] if audio_src else None!r}...")

        # Lyrics text — look for a visible lyric line we know was generated.
        lyric_present = await page.locator("text=/\\b(rain|night|coffee|garden|stars|book)\\b/i").count()
        print(f"    lyric-text matches: {lyric_present}")

        # ShortsPlayer surface — check for one of the three states' text.
        for label in [
            "Shorts video coming soon",
            "Generating short",
            "Short couldn't be generated",
            "Download MP4",
        ]:
            n = await page.locator(f"text={label}").count()
            print(f"    text={label!r}: {n}")

        # MusicVideoSection (still mounted per cohabitation) should also exist.
        for label in ["Watch", "music video", "Music video"]:
            n = await page.locator(f"text={label}").count()
            print(f"    text={label!r}: {n}")

        await browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

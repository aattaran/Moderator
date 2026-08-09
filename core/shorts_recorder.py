"""Playwright headless driver for the comments-song Shorts MP4 export.

Reuses the live in-browser compositor (canvas + MediaRecorder) — see
apps/web/components/ShortsSection.tsx and apps/web/lib/shorts-export.ts in
the comments-song repo. This module does NOT re-implement compositing;
it just drives the page so the existing renderer produces the same MP4 the
user would get by clicking "Start recording" themselves.

Recording is REAL-TIME — a 2:30 song takes ~2:30 of wall clock to record,
plus a few seconds of MediaRecorder finalization. Plan timeouts accordingly.

Verified selectors (DOM-inspected on 2026-05-02 against
https://comments-song.app/v/<id>/<hash>):
- Start recording button: `button:has-text('Start recording')`
  - Enabled state: no [disabled] attribute. Use `:not([disabled])` selector.
  - Initial state (artwork-pending): `disabled=""` until cover-art arrives.
- Download anchor (after recording): `a[download]` with href=blob:..., the
  `download` attribute carries the filename ShortsSection.buildFileName()
  produced (`<sanitized_title>-<videoId>.mp4` or .webm).
"""

import asyncio
import logging
from pathlib import Path

from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

logger = logging.getLogger(__name__)


class ShortsRecorderError(RuntimeError):
    """Base error for shorts recorder failures."""


class CoverArtTimeout(ShortsRecorderError):
    """The Start recording button did not enable in time — cover-art is stuck.

    The pipeline should mark this prompt as cover_art_timeout and skip to the
    next prompt; the underlying song is still queryable and may finish later.
    """


class RecordingTimeout(ShortsRecorderError):
    """The download anchor never appeared — the recording never finished."""


async def record_song(
    song_url: str,
    output_path: str | Path,
    cover_art_timeout_ms: int = 120_000,
    download_timeout_ms: int = 240_000,
    nav_timeout_ms: int = 30_000,
) -> Path:
    """Record a comments-song page's Shorts export to output_path.

    Args:
        song_url: Full URL to the song page, e.g.
            https://comments-song.app/v/ft_abc.../929260ad9b9ea9fe
        output_path: Where to save the recorded video. The ShortsSection picks
            mp4 in Chromium, so .mp4 is the expected extension. The bytes are
            the same valid container regardless of the suffix you pass.
        cover_art_timeout_ms: How long to wait for the Start recording button
            to enable. Default 2 min — the cover-art KIE callback usually
            arrives well within that, but on KIE backlogs it can take longer.
        download_timeout_ms: How long to wait for the recording to finish
            and the download anchor to appear. Should be at least
            song_duration + 30s. Default 4 min covers a 2:30 song with
            ample margin.
        nav_timeout_ms: Page navigation timeout.

    Returns:
        The absolute Path to the saved file.

    Raises:
        CoverArtTimeout: button never enabled.
        RecordingTimeout: download anchor never appeared.
        ShortsRecorderError: navigation failed or saved file is too small.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                # Required: handleStart() calls audio.play() — Playwright clicks
                # already count as user gestures, but this flag avoids any
                # autoplay-policy edge case in headless mode.
                "--autoplay-policy=no-user-gesture-required",
                # Force GPU off — canvas.captureStream() in headless is more
                # reliable on the SwiftShader / software path on this machine.
                "--use-gl=swiftshader",
            ],
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        await page.bring_to_front()

        try:
            logger.info("shorts: navigate %s", song_url)
            resp = await page.goto(song_url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            if not resp or resp.status != 200:
                status = resp.status if resp else "?"
                raise ShortsRecorderError(f"shorts: navigate failed status={status}")

            # 1. Wait for the Start recording button to enable. The artwork-mid-mount
            #    fix (08e42a1) transitions the page from artwork-pending -> idle
            #    when cover-art arrives. The locator selects only the enabled
            #    instance via :not([disabled]); if the button is currently in
            #    its disabled-with-explanatory-paragraph form (line 445), the
            #    locator simply waits.
            logger.info(
                "shorts: waiting for Start recording button to enable (timeout=%dms)",
                cover_art_timeout_ms,
            )
            start_button = page.locator("button:has-text('Start recording'):not([disabled])")
            try:
                await start_button.wait_for(state="visible", timeout=cover_art_timeout_ms)
            except PlaywrightTimeout as e:
                raise CoverArtTimeout(
                    f"shorts: Start recording button did not enable in {cover_art_timeout_ms}ms "
                    f"on {song_url}"
                ) from e

            # 2. Set up download interception. The whole recording window must
            #    fit inside this with-block — start_button.click() kicks off
            #    real-time recording, then we wait for the <a download> anchor
            #    to appear, then click it which fires the actual download event.
            logger.info("shorts: clicking Start recording (real-time recording begins)")
            async with page.expect_download(timeout=download_timeout_ms) as dl_info:
                await start_button.click()

                # 3. Wait for the recorder to finish and the download anchor
                #    to mount. Until then the page shows a Cancel button and
                #    a recording progress indicator.
                logger.info(
                    "shorts: waiting for download anchor (a[download]) to appear "
                    "(timeout=%dms)", download_timeout_ms,
                )
                anchor = page.locator("a[download]").first
                try:
                    await anchor.wait_for(state="visible", timeout=download_timeout_ms)
                except PlaywrightTimeout as e:
                    # Probe the page for an error UI that handleStart sets when
                    # MediaRecorder construction or audio.play() fails.
                    err_text = await _probe_error_message(page)
                    raise RecordingTimeout(
                        f"shorts: download anchor not visible in {download_timeout_ms}ms"
                        + (f" — page error: {err_text}" if err_text else "")
                    ) from e

                suggested = await anchor.get_attribute("download")
                logger.info("shorts: download anchor visible (suggested filename=%s)", suggested)

                # 4. Click the anchor to trigger the actual file save.
                await anchor.click()

            download = await dl_info.value
            logger.info(
                "shorts: download intercepted (suggested_filename=%s) — saving to %s",
                download.suggested_filename, output_path,
            )
            await download.save_as(str(output_path))

            size = output_path.stat().st_size
            logger.info("shorts: saved %s (%d bytes)", output_path, size)
            if size < 100_000:
                raise ShortsRecorderError(
                    f"shorts: saved file at {output_path} is too small ({size} bytes); "
                    f"recording likely failed silently"
                )
            return output_path
        finally:
            await browser.close()


async def _probe_error_message(page) -> str | None:
    """Return any error text the ShortsSection rendered.

    handleStart sets `{ kind: 'error', message: ... }` on failure, and the UI
    renders that message in plain text. Best-effort: returns None if no
    obvious error text is on the page.
    """
    try:
        # Common error prefix used by handleStart's catch.
        for phrase in ("Couldn't start", "Refs not ready"):
            loc = page.get_by_text(phrase, exact=False)
            if await loc.count() > 0:
                return (await loc.first.text_content() or "").strip()
    except Exception:
        return None
    return None

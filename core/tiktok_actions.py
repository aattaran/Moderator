"""TikTok web browser actions using Playwright."""

import asyncio
import logging
import os

from playwright.async_api import async_playwright, BrowserContext, Page

from core import tiktok_selectors as S

logger = logging.getLogger(__name__)

# Generous enough for a cold residential-proxy connection, which is several times
# slower than a direct one. Only ever spent when the page is genuinely slow —
# wait_for_selector returns as soon as the element appears.
SPA_RENDER_TIMEOUT_MS = 60000
# TikTok's Studio SPA intermittently crashes on load; a reload clears it.
COMPOSER_ATTEMPTS = 3
# Upload must finish before Post is clicked, or the video is silently discarded.
UPLOAD_TIMEOUT_S = 240


class TikTokActions:
    """Browser actions for TikTok video posting and engagement."""

    def __init__(
        self,
        auth_state_file: str = "data/tiktok_auth_state.json",
        proxy_server: str = "",
        proxy_username: str = "",
        proxy_password: str = "",
    ):
        self.auth_state_file = auth_state_file
        self.proxy_server = proxy_server
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self):
        """Launch browser context for TikTok."""
        self._playwright = await async_playwright().start()

        # Route through the residential proxy when configured. The session cookies are
        # created on a residential IP; posting from the droplet's datacenter IP without
        # this is the clearest automation signal TikTok gets. Set at launch because
        # Chromium ignores context-level proxies unless the browser was launched with one.
        proxy = None
        if self.proxy_server:
            proxy = {"server": self.proxy_server}
            if self.proxy_username:
                proxy["username"] = self.proxy_username
                proxy["password"] = self.proxy_password
            logger.info("TikTok: routing through proxy %s", self.proxy_server)

        self._browser = await self._playwright.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                   "--disable-blink-features=AutomationControlled"],
        )

        storage_state = self.auth_state_file if os.path.exists(self.auth_state_file) else None

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            storage_state=storage_state,
        )
        self._page = await self._context.new_page()

        if storage_state:
            logger.info("TikTok: loaded auth state from %s", self.auth_state_file)
        logger.info("TikTok browser started")

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("TikTok browser not started")
        return self._page

    async def _human_delay(self, min_ms: int = 1000, max_ms: int = 3000):
        import random
        await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    async def _open_composer(self, attempts: int = COMPOSER_ATTEMPTS) -> bool:
        """Load the upload composer, retrying transient render failures.

        TikTok's Studio SPA intermittently dies on load with a client-side
        "Unexpected Application Error!" (measured ~1 in 4 loads over a residential
        proxy). It is a TikTok bug, not a block or an expired session — a plain
        reload clears it, so a single-shot navigation loses posts for no reason.
        """
        for attempt in range(1, attempts + 1):
            try:
                await self.page.goto(S.STUDIO_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)

                if "/login" in self.page.url:
                    logger.warning("TikTok: redirected to login — session expired")
                    return False

                await self.page.wait_for_selector(
                    S.FILE_INPUT, state="attached", timeout=SPA_RENDER_TIMEOUT_MS
                )
                return True
            except Exception as e:
                logger.warning(
                    "TikTok: composer did not render (attempt %d/%d): %s",
                    attempt, attempts, str(e).splitlines()[0],
                )
                if attempt < attempts:
                    await self._human_delay(3000, 6000)

        logger.error("TikTok: composer failed to render after %d attempts", attempts)
        return False

    async def is_logged_in(self) -> bool:
        """Check if the session can still reach the Studio upload page.

        Probes the Studio upload widget rather than the home-page profile icon:
        TikTok stopped rendering PROFILE_ICON on the home page, so the old check
        reported False on a perfectly valid session.
        """
        try:
            if not await self._open_composer():
                return False
            return await self.page.query_selector(S.LOGIN_MODAL) is None
        except Exception as e:
            logger.warning("TikTok: login check failed: %s", e)
            return False

    async def _dismiss_overlays(self) -> None:
        """Strip onboarding coach-marks that swallow clicks.

        TikTok's react-joyride overlay covers the composer and intercepts pointer
        events, which can silently block the Post button. It carries no state we
        need, so removing the nodes is safe.
        """
        try:
            removed = await self.page.evaluate(
                """(sel) => {
                    const nodes = document.querySelectorAll(sel);
                    nodes.forEach(n => n.remove());
                    return nodes.length;
                }""",
                S.JOYRIDE_NODES,
            )
            if removed:
                logger.info("TikTok: removed %d onboarding overlay node(s)", removed)
        except Exception as e:
            logger.warning("TikTok: could not clear overlays: %s", e)

    async def _visibility_control(self):
        """Return the audience Select next to the 'Who can see this post' label."""
        handle = await self.page.evaluate_handle(
            """([label, trigger]) => {
                const leaves = [...document.querySelectorAll('*')].filter(
                    el => el.children.length === 0 && el.textContent.trim() === label);
                if (!leaves.length) return null;
                let node = leaves[0];
                for (let i = 0; i < 6 && node.parentElement; i++) {
                    node = node.parentElement;
                    const t = node.querySelector(trigger);
                    if (t) return t;
                }
                return null;
            }""",
            [S.VISIBILITY_LABEL, S.SELECT_TRIGGER],
        )
        return handle.as_element()

    async def _ensure_public(self) -> bool:
        """Guarantee the post is visible to Everyone, or refuse to publish.

        The audience is never set explicitly by the composer — it reuses whatever was
        last selected on the account. Posting to "Friends" or "Only you" would look
        identical in our logs, so this reads the control and corrects it, and returns
        False rather than publishing something non-public.
        """
        try:
            control = await self._visibility_control()
            if control is None:
                logger.error("TikTok: audience control not found — refusing to post")
                return False

            current = (await control.inner_text()).strip()
            if current == S.VISIBILITY_PUBLIC:
                logger.info("TikTok: audience is %s", current)
                return True

            logger.warning("TikTok: audience was %r, setting to %s", current, S.VISIBILITY_PUBLIC)
            await control.click()
            await self._human_delay(1000, 2000)

            for opt in await self.page.query_selector_all(S.SELECT_OPTION):
                try:
                    if (await opt.inner_text()).strip() == S.VISIBILITY_PUBLIC and await opt.is_visible():
                        await opt.click()
                        await self._human_delay(1000, 2000)
                        break
                except Exception as e:
                    logger.warning("TikTok: could not read audience option: %s", e)
                    continue

            control = await self._visibility_control()
            confirmed = (await control.inner_text()).strip() if control else ""
            if confirmed != S.VISIBILITY_PUBLIC:
                logger.error("TikTok: audience still %r — refusing to post", confirmed)
                return False

            logger.info("TikTok: audience corrected to %s", confirmed)
            return True
        except Exception as e:
            logger.error("TikTok: audience check failed (%s) — refusing to post", e)
            return False

    async def _wait_for_upload_complete(self, timeout_s: int = UPLOAD_TIMEOUT_S) -> bool:
        """Block until TikTok reports the file uploaded and the Post button is live.

        Clicking Post mid-upload does not publish — it triggers the navigation-confirm
        modal and the video is lost. The old fixed 15-25s sleep was enough on a direct
        connection and not enough over a proxy, which is exactly how that failure showed up.
        """
        deadline = timeout_s
        waited = 0
        while waited < deadline:
            await asyncio.sleep(5)
            waited += 5
            try:
                body = " ".join((await self.page.inner_text("body")).split())
                if "Uploaded" not in body:
                    continue
                btn = await self.page.query_selector(S.POST_BUTTON)
                if btn and await btn.is_visible() and not await btn.is_disabled():
                    logger.info("TikTok: upload complete after %ds", waited)
                    return True
            except Exception:
                continue

        logger.error("TikTok: upload did not complete within %ds", timeout_s)
        return False

    async def post_video(self, video_path: str, caption: str) -> bool:
        """Upload and post a video to TikTok."""
        try:
            # Load the composer, retrying TikTok's transient SPA crash.
            if not await self._open_composer():
                await self.page.screenshot(path="data/tiktok_upload_debug.png")
                return False

            # Dismiss any popups/cookies
            for sel in ['button:has-text("Accept")', 'button:has-text("OK")', '[aria-label="Close"]']:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await self._human_delay(1000, 2000)
                except Exception as e:
                    # Absent popups are the normal case and do not raise; an actual
                    # exception here means the page moved under us, so say so.
                    logger.warning("TikTok: popup dismiss failed for %s: %s", sel, e)

            await self.page.screenshot(path="data/tiktok_upload_page.png")

            # Find file input — check main page and all iframes
            file_input = None

            # Try main page first
            for sel in [S.FILE_INPUT, 'input[type="file"]', 'input[accept*="video"]']:
                file_input = await self.page.query_selector(sel)
                if file_input:
                    break

            # Check iframes
            if not file_input:
                for frame in self.page.frames:
                    for sel in ['input[type="file"]', 'input[accept*="video"]']:
                        file_input = await frame.query_selector(sel)
                        if file_input:
                            break
                    if file_input:
                        break

            # Try clicking upload/select button to reveal file input
            if not file_input:
                for sel in [S.UPLOAD_BUTTON, 'button:has-text("Select")', 'div:has-text("Select video")']:
                    upload_btn = await self.page.query_selector(sel)
                    if upload_btn:
                        await upload_btn.click()
                        await self._human_delay(2000, 3000)
                        break
                # Try again after clicking
                for sel in ['input[type="file"]', S.FILE_INPUT]:
                    file_input = await self.page.query_selector(sel)
                    if file_input:
                        break

            if not file_input:
                logger.error("TikTok: could not find file input")
                await self.page.screenshot(path="data/tiktok_upload_debug.png")
                return False

            # Upload video
            await file_input.set_input_files(video_path)
            logger.info("TikTok: video file selected, waiting for upload...")
            if not await self._wait_for_upload_complete():
                await self.page.screenshot(path="data/tiktok_upload_debug.png")
                return False

            # Dismiss any tooltips/overlays that appeared
            for sel in ['button:has-text("Got it")', 'button:has-text("OK")', '[aria-label="Close"]', '.tooltip-close', 'button:has-text("Dismiss")']:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await self._human_delay(500, 1000)
                except Exception as e:
                    logger.warning("TikTok: tooltip dismiss failed for %s: %s", sel, e)

            await self.page.screenshot(path="data/tiktok_after_upload.png")

            # Enter caption — try multiple selectors
            caption_input = None
            for sel in [
                S.CAPTION_EDITOR,
                S.CAPTION_INPUT,
                '[contenteditable="true"]',
                'div[data-contents="true"]',
                '.public-DraftEditor-content',
                'div[role="textbox"]',
            ]:
                caption_input = await self.page.query_selector(sel)
                if caption_input:
                    break

            if caption_input:
                await caption_input.click()
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.press("Backspace")
                await self._human_delay(500, 1000)
                await self.page.keyboard.type(caption[:300], delay=10)
                await self._human_delay(1000, 2000)
                logger.info("TikTok: caption entered")
            else:
                logger.warning("TikTok: could not find caption input")

            # Coach-mark overlays intercept clicks; clear them before the audience
            # control and the Post button are touched.
            await self._dismiss_overlays()

            # Never publish without confirming the post is visible to Everyone.
            if not await self._ensure_public():
                await self.page.screenshot(path="data/tiktok_privacy_debug.png")
                return False

            # Click Post. Only the stable data-e2e hook, plus an EXACT-text fallback —
            # substring matching ('button:has-text("Post")') resolves to the sidebar nav
            # button first and silently discards the upload.
            post_btn = await self.page.query_selector(S.POST_BUTTON)
            if post_btn and not await post_btn.is_visible():
                post_btn = None

            if not post_btn:
                for candidate in await self.page.query_selector_all("button"):
                    try:
                        label = (await candidate.inner_text()).strip().lower()
                        if label == "post" and await candidate.is_visible():
                            post_btn = candidate
                            logger.warning("TikTok: data-e2e hook missing, used exact-text fallback")
                            break
                    except Exception:
                        continue

            if not post_btn:
                logger.error("TikTok: could not find Post button")
                await self.page.screenshot(path="data/tiktok_post_debug.png")
                return False

            await post_btn.click()
            await self._human_delay(10000, 15000)

            # A misclick that navigates away raises the exit-confirm modal. Cancel it so
            # we stay on the composer and report failure instead of losing the upload.
            #
            # Gate on the modal's own TEXT. Matching a bare visible "Cancel" button is
            # not specific enough: TikTok shows its own dialog after a SUCCESSFUL Post
            # click that also carries a Cancel, and cancelling that aborts the publish.
            try:
                body = " ".join((await self.page.inner_text("body")).split())
                if S.EXIT_CONFIRM_TEXT in body:
                    cancel = await self.page.query_selector(S.EXIT_CONFIRM_CANCEL)
                    if cancel and await cancel.is_visible():
                        await cancel.click()
                    logger.error("TikTok: Post click hit a navigation control — not published")
                    await self.page.screenshot(path="data/tiktok_post_debug.png")
                    return False
            except Exception as e:
                # Not fatal: _verify_published below is ground truth either way, but a
                # failure here means we could not tell a misclick from a real post.
                logger.warning("TikTok: exit-modal check failed: %s", e)

            # Never report success on the click alone — verify against the creator's
            # own post list, which is ground truth for whether it published.
            published = await self._verify_published(caption)
            if published:
                logger.info("TikTok: video posted successfully")
            else:
                logger.error("TikTok: Post clicked but video not found in content list")
                await self.page.screenshot(path="data/tiktok_post_debug.png")
            return published

        except Exception as e:
            logger.error("TikTok: failed to post video: %s", e)
            try:
                await self.page.screenshot(path="data/tiktok_error_debug.png")
            except Exception as shot_err:
                logger.warning("TikTok: could not capture error screenshot: %s", shot_err)
            return False

    async def _verify_published(self, caption: str, attempts: int = 4) -> bool:
        """Confirm the video reached the creator's post list.

        TikTok processes the upload server-side after the Post click, so poll rather
        than checking once. Matches on a distinctive caption prefix.
        """
        needle = " ".join(caption.split())[:40].strip()
        if not needle:
            logger.warning("TikTok: empty caption — cannot verify publication")
            return False

        for attempt in range(attempts):
            try:
                await self.page.goto(S.STUDIO_CONTENT_URL, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(8)
                body = " ".join((await self.page.inner_text("body")).split())
                if needle in body:
                    return True
                logger.info("TikTok: not in content list yet (attempt %d/%d)", attempt + 1, attempts)
            except Exception as e:
                logger.warning("TikTok: verification attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(15)

        return False

    async def like_video(self, video_index: int = 0) -> bool:
        """Like a video on the For You feed."""
        try:
            await self.page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=15000)
            await self._human_delay(3000, 5000)

            like_btn = await self.page.query_selector(S.LIKE_BUTTON)
            if like_btn:
                await like_btn.click()
                await self._human_delay(500, 1000)
                logger.info("TikTok: liked video")
                return True
            return False
        except Exception as e:
            logger.error("TikTok: failed to like: %s", e)
            return False

    async def comment_on_video(self, text: str) -> bool:
        """Comment on the current video."""
        try:
            comment_input = await self.page.query_selector(S.COMMENT_INPUT)
            if comment_input:
                await comment_input.click()
                await self.page.keyboard.type(text, delay=20)
                await self._human_delay(500, 1000)

                submit = await self.page.query_selector(S.COMMENT_SUBMIT)
                if submit:
                    await submit.click()
                else:
                    await self.page.keyboard.press("Enter")
                await self._human_delay(2000, 3000)
                logger.info("TikTok: commented on video")
                return True
            return False
        except Exception as e:
            logger.error("TikTok: failed to comment: %s", e)
            return False

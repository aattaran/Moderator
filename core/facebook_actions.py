"""Facebook Group browser actions using Playwright."""

import asyncio
import logging

from core.playwright_browser import PlaywrightBrowser
from core import facebook_selectors as S

logger = logging.getLogger(__name__)

GROUP_URL = "https://www.facebook.com/groups/773954008871273"


class FacebookActions:
    """Browser actions for Facebook Group management."""

    def __init__(self, browser: PlaywrightBrowser):
        self.b = browser

    async def _switch_to_page_identity(self):
        """Switch posting identity from personal profile to ELEMNT Page in the group."""
        try:
            # Look for the "posting as" or identity switcher in the group
            # Facebook groups show a profile picture near "Write something" — clicking it opens identity menu
            for sel in [
                # The identity switcher button (shows current posting identity)
                '[aria-label*="Posting as"]',
                '[aria-label*="posting as"]',
                # The profile pic next to "Write something" that opens identity menu
                'div[role="button"] image',
                # Direct "Switch" or profile selector
                'span:has-text("Switch")',
            ]:
                try:
                    btn = await self.b.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await self.b.human_delay(2000, 3000)

                        # Look for ELEMNT in the identity options
                        for page_sel in [
                            'span:has-text("Elemnt")',
                            'span:has-text("ELEMNT")',
                            'span:has-text("elemnt")',
                            '[role="menuitem"]:has-text("Elemnt")',
                            '[role="option"]:has-text("Elemnt")',
                            '[role="radio"]:has-text("Elemnt")',
                        ]:
                            page_option = await self.b.page.query_selector(page_sel)
                            if page_option and await page_option.is_visible():
                                await page_option.click()
                                await self.b.human_delay(1000, 2000)
                                logger.info("Switched posting identity to ELEMNT Page")
                                return
                except Exception:
                    continue

            logger.debug("No identity switcher found — may already be posting as Page")
        except Exception as e:
            logger.debug("Identity switch attempt: %s", e)

    async def ensure_on_facebook(self):
        """Make sure we're on facebook.com and logged in."""
        url = self.b.page.url
        if "facebook.com" not in url:
            await self.b.goto("https://www.facebook.com")
        # Check for login form
        login = await self.b.page.query_selector(S.LOGIN_FORM)
        if login:
            raise RuntimeError("Facebook session expired — manual login required")

    async def post_to_group(self, text: str) -> bool:
        """Post text content to the Facebook Group."""
        try:
            await self.ensure_on_facebook()
            await self.b.page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=60000)
            await self.b.human_delay(8000, 12000)

            # Dismiss any popups
            for dismiss in ['[aria-label="Close"]', 'button:has-text("Not Now")', 'button:has-text("OK")']:
                try:
                    btn = await self.b.page.query_selector(dismiss)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await self.b.human_delay(1000, 2000)
                except Exception:
                    pass

            # Take screenshot for debugging
            await self.b.page.screenshot(path="data/fb_group_page.png")

            # Switch to posting as ELEMNT Page (not personal profile)
            await self._switch_to_page_identity()

            # Click "Write something" to open composer — try multiple selectors
            prompt = None
            for sel in [
                S.CREATE_POST_PROMPT,
                S.CREATE_POST_PROMPT_ALT,
                'span:has-text("Write something")',
                'div[role="button"] span:has-text("Write")',
                '[aria-label*="Write"]',
                '[aria-label*="Create"]',
                'div[role="button"]:has-text("What\'s on your mind")',
            ]:
                prompt = await self.b.page.query_selector(sel)
                if prompt and await prompt.is_visible():
                    break
                prompt = None

            if not prompt:
                logger.error("Could not find post composer")
                await self.b.page.screenshot(path="data/fb_composer_fail.png")
                return False

            await prompt.click()
            await self.b.human_delay(3000, 5000)

            # Type in the composer — scoped to dialog
            text_input = None
            for sel in [
                S.POST_TEXT_INPUT,
                '[role="dialog"] [contenteditable="true"][role="textbox"]',
                '[role="dialog"] [data-lexical-editor="true"]',
                '[role="textbox"][aria-placeholder*="public post"]',
                '[role="dialog"] [contenteditable="true"]',
            ]:
                try:
                    text_input = await self.b.page.wait_for_selector(sel, timeout=5000)
                    if text_input:
                        break
                except Exception:
                    continue

            if not text_input:
                logger.error("Could not find text input")
                return False

            await text_input.click()
            await self.b.page.keyboard.type(text, delay=15)
            await self.b.human_delay(1000, 2000)

            # Click Post — try multiple selectors
            post_btn = None
            for sel in [
                S.POST_SUBMIT,
                S.POST_SUBMIT_ALT,
                '[aria-label="Post"]',
                'div[aria-label="Post"]',
                'button:has-text("Post")',
            ]:
                post_btn = await self.b.page.query_selector(sel)
                if post_btn and await post_btn.is_visible():
                    break
                post_btn = None

            if post_btn:
                await post_btn.click()
                await self.b.human_delay(5000, 8000)
                logger.info("Posted to Facebook Group")
                return True

            logger.error("Could not find Post button")
            return False
        except Exception as e:
            logger.error("Failed to post to group: %s", e)
            return False

    async def post_to_group_with_image(self, text: str, image_path: str) -> bool:
        """Post text + image to the Facebook Group."""
        try:
            await self.ensure_on_facebook()
            await self.b.page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=60000)
            await self.b.human_delay(8000, 12000)

            # Switch to ELEMNT Page identity
            await self._switch_to_page_identity()

            # Open composer
            prompt = await self.b.page.query_selector(S.CREATE_POST_PROMPT)
            if not prompt:
                prompt = await self.b.page.query_selector('span:has-text("Write something")')
            if prompt:
                await prompt.click()
                await self.b.human_delay(2000, 3000)

            # Click photo/video button
            photo_btn = await self.b.page.query_selector('[aria-label="Photo/video"]')
            if photo_btn:
                await photo_btn.click()
                await self.b.human_delay(1000, 2000)

            # Upload file
            file_input = await self.b.page.query_selector('input[type="file"][accept*="image"]')
            if file_input:
                await file_input.set_input_files(image_path)
                await self.b.human_delay(3000, 5000)

            # Type text
            text_input = await self.b.page.wait_for_selector(
                S.POST_TEXT_INPUT, timeout=10000
            )
            await text_input.click()
            await self.b.page.keyboard.type(text, delay=15)
            await self.b.human_delay(1000, 2000)

            # Post
            post_btn = await self.b.page.query_selector(S.POST_SUBMIT)
            if not post_btn:
                post_btn = await self.b.page.query_selector(S.POST_SUBMIT_ALT)
            if post_btn:
                await post_btn.click()
                await self.b.human_delay(3000, 5000)
                logger.info("Posted to Facebook Group with image")
                return True

            return False
        except Exception as e:
            logger.error("Failed to post with image: %s", e)
            return False

    async def comment_on_group_post(self, post_index: int, text: str) -> bool:
        """Comment on a post in the group feed (by index, 0 = first post)."""
        try:
            await self.ensure_on_facebook()
            await self.b.goto(GROUP_URL)
            await self.b.human_delay(3000, 5000)

            posts = await self.b.query_all(S.POST_ARTICLE)
            if post_index >= len(posts):
                logger.warning("Post index %d not found (only %d posts)", post_index, len(posts))
                return False

            post = posts[post_index]

            # Click comment button/area
            comment_btn = await post.query_selector(S.COMMENT_BUTTON)
            if comment_btn:
                await comment_btn.click()
                await self.b.human_delay(1000, 2000)

            # Find comment input
            comment_input = await self.b.page.wait_for_selector(
                S.COMMENT_INPUT, timeout=10000
            )
            await comment_input.click()
            await self.b.page.keyboard.type(text, delay=20)
            await self.b.human_delay(500, 1000)

            # Submit with Enter
            await self.b.page.keyboard.press("Enter")
            await self.b.human_delay(2000, 3000)
            logger.info("Commented on group post")
            return True
        except Exception as e:
            logger.error("Failed to comment: %s", e)
            return False

    async def like_group_post(self, post_index: int) -> bool:
        """Like a post in the group feed."""
        try:
            await self.ensure_on_facebook()
            await self.b.goto(GROUP_URL)
            await self.b.human_delay(3000, 5000)

            posts = await self.b.query_all(S.POST_ARTICLE)
            if post_index >= len(posts):
                return False

            like_btn = await posts[post_index].query_selector(S.LIKE_BUTTON)
            if like_btn:
                await like_btn.click()
                await self.b.human_delay(500, 1000)
                logger.info("Liked group post")
                return True
            return False
        except Exception as e:
            logger.error("Failed to like post: %s", e)
            return False

    async def get_group_feed(self, max_count: int = 10) -> list[dict]:
        """Read posts from the group feed."""
        try:
            await self.ensure_on_facebook()
            await self.b.goto(GROUP_URL)
            await self.b.human_delay(3000, 5000)

            # Scroll to load more posts
            for _ in range(2):
                await self.b.scroll_down(600)
                await self.b.human_delay(1000, 2000)

            posts = await self.b.query_all(S.POST_ARTICLE)
            feed = []
            for post in posts[:max_count]:
                try:
                    text_el = await post.query_selector(S.POST_TEXT)
                    text = (await text_el.text_content() or "") if text_el else ""
                    feed.append({"text": text.strip()[:200]})
                except Exception:
                    continue

            logger.info("Read %d posts from group feed", len(feed))
            return feed
        except Exception as e:
            logger.error("Failed to read group feed: %s", e)
            return []

    async def approve_pending_members(self, max_count: int = 20) -> int:
        """Approve pending member requests."""
        try:
            await self.ensure_on_facebook()
            await self.b.goto(f"{GROUP_URL}/member-requests")
            await self.b.human_delay(3000, 5000)

            approved = 0
            approve_buttons = await self.b.query_all(S.APPROVE_BUTTON)

            for btn in approve_buttons[:max_count]:
                try:
                    await btn.click()
                    await self.b.human_delay(1000, 2000)
                    approved += 1
                except Exception:
                    continue

            logger.info("Approved %d pending members", approved)
            return approved
        except Exception as e:
            logger.error("Failed to approve members: %s", e)
            return 0

    async def is_logged_in(self) -> bool:
        """Check if logged into Facebook."""
        try:
            await self.b.page.goto(
                "https://www.facebook.com", wait_until="domcontentloaded", timeout=15000
            )
            await asyncio.sleep(5)
            url = self.b.page.url
            if "login" in url or "checkpoint" in url:
                return False
            profile = await self.b.page.query_selector(S.PROFILE_LINK)
            return profile is not None or "facebook.com" in url
        except Exception:
            return False

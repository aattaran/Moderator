"""Playwright-based browser session for X.com automation."""

import asyncio
import logging
import random

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from core.x_selectors import USER_AVATAR, LOGIN_BUTTON

logger = logging.getLogger(__name__)


class PlaywrightBrowser:
    """Manages a Chromium browser session via Playwright."""

    def __init__(self, user_data_dir: str, headless: bool = True, auth_state_file: str = "data/auth_state.json",
                 proxy_server: str = "", proxy_username: str = "", proxy_password: str = ""):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._auth_state_file = auth_state_file
        self._proxy_server = proxy_server
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self):
        """Launch browser and load auth state."""
        import os
        self._playwright = await async_playwright().start()

        # Build proxy config if provided
        launch_kwargs = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        }
        if self._proxy_server:
            launch_kwargs["proxy"] = {"server": self._proxy_server}
            if self._proxy_username:
                launch_kwargs["proxy"]["username"] = self._proxy_username
                launch_kwargs["proxy"]["password"] = self._proxy_password
            logger.info("Using proxy: %s", self._proxy_server)

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        # Load auth state file directly as storage_state if it exists
        auth_file = self._auth_state_file
        storage_state = auth_file if os.path.exists(auth_file) else None

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
            logger.info("Loaded auth state from %s", auth_file)

        logger.info("Playwright browser started (headless=%s)", self.headless)

    async def stop(self):
        """Close browser and Playwright."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._page = None
        self._browser = None
        self._playwright = None
        logger.info("Playwright browser stopped")

    async def __aenter__(self):
        if not self._page:
            await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Keep browser alive between tasks — only stop explicitly
        pass

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def goto(self, url: str, wait_until: str = "networkidle"):
        """Navigate to URL."""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=30000)
        except Exception:
            # Fallback if networkidle times out
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self.human_delay(2000, 4000)

    async def click(self, selector: str, timeout: int = 10000):
        """Click an element."""
        await self.page.click(selector, timeout=timeout)
        await self.human_delay(300, 800)

    async def fill(self, selector: str, text: str):
        """Clear and fill a text field."""
        await self.page.fill(selector, text, timeout=10000)
        await self.human_delay(200, 500)

    async def type_text(self, selector: str, text: str, delay: int = 30):
        """Type text character by character (more human-like)."""
        await self.page.click(selector, timeout=10000)
        await self.page.keyboard.type(text, delay=delay)
        await self.human_delay(300, 600)

    async def upload_file(self, selector: str, file_path: str):
        """Upload a file via a file input."""
        await self.page.set_input_files(selector, file_path, timeout=10000)
        await self.human_delay(2000, 4000)

    async def wait_for(self, selector: str, timeout: int = 10000, state: str = "visible"):
        """Wait for a selector to be visible."""
        return await self.page.wait_for_selector(selector, timeout=timeout, state=state)

    async def wait_gone(self, selector: str, timeout: int = 10000):
        """Wait for a selector to disappear."""
        await self.page.wait_for_selector(selector, state="hidden", timeout=timeout)

    async def query_all(self, selector: str):
        """Get all matching elements."""
        return await self.page.query_selector_all(selector)

    async def get_text(self, selector: str) -> str:
        """Get text content of first matching element."""
        el = await self.page.query_selector(selector)
        if el:
            return (await el.text_content() or "").strip()
        return ""

    async def scroll_down(self, pixels: int = 500):
        """Scroll the page down."""
        await self.page.mouse.wheel(0, pixels)
        await self.human_delay(500, 1000)

    async def is_logged_in(self) -> bool:
        """Check if we're logged into X by navigating to home."""
        try:
            await self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(5)
            url = self.page.url
            # If redirected to login, we're not logged in
            if "/login" in url or "/i/flow/login" in url:
                return False
            # If we stayed on /home, we're logged in
            if "/home" in url:
                return True
            el = await self.page.query_selector(USER_AVATAR)
            return el is not None
        except Exception:
            return False

    async def screenshot(self, path: str):
        """Take a debug screenshot."""
        await self.page.screenshot(path=path)

    @staticmethod
    async def human_delay(min_ms: int = 200, max_ms: int = 800):
        """Random delay to mimic human behavior."""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)

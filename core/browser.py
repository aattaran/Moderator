"""Browser lifecycle management for Computer Use."""

import asyncio
import logging
import os
import signal

logger = logging.getLogger(__name__)


class BrowserSession:
    """Manages the Firefox browser process lifecycle.

    Used as an async context manager to ensure browser is running
    before agent tasks and cleaned up after.
    """

    def __init__(self, profile_path: str, display: str = ":1"):
        self.profile_path = profile_path
        self.display = display
        self._process: asyncio.subprocess.Process | None = None

    async def __aenter__(self):
        await self.ensure_running()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Don't kill the browser on exit — it persists across tasks
        pass

    async def ensure_running(self) -> bool:
        """Ensure Firefox is running. Start it if not."""
        if await self._is_running():
            logger.debug("Firefox is already running")
            return True
        logger.info("Starting Firefox with profile: %s", self.profile_path)
        return await self._launch()

    async def _is_running(self) -> bool:
        """Check if a Firefox window exists."""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"DISPLAY={self.display} xdotool search --name 'Mozilla Firefox'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return bool(stdout.strip())
        except (asyncio.TimeoutError, Exception):
            return False

    async def _launch(self) -> bool:
        """Launch Firefox with the persistent profile."""
        os.makedirs(self.profile_path, exist_ok=True)
        cmd = (
            f"DISPLAY={self.display} firefox-esr "
            f"--profile {self.profile_path} "
            f"--no-remote "
            f"--width 1024 --height 768 "
            f"https://x.com"
        )
        self._process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # Wait for the window to appear
        for attempt in range(15):
            await asyncio.sleep(1)
            if await self._is_running():
                logger.info("Firefox started successfully")
                return True
            logger.debug("Waiting for Firefox window... (%d/15)", attempt + 1)

        logger.error("Firefox failed to start within 15 seconds")
        return False

    async def navigate_to(self, url: str):
        """Navigate the browser to a URL using keyboard shortcut.

        Uses Ctrl+L (focus address bar) which is more reliable than
        clicking the address bar.
        """
        proc = await asyncio.create_subprocess_shell(
            f"DISPLAY={self.display} xdotool key ctrl+l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        await asyncio.sleep(0.3)

        # Clear existing URL and type new one
        await asyncio.create_subprocess_shell(
            f"DISPLAY={self.display} xdotool key ctrl+a",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.1)

        await asyncio.create_subprocess_shell(
            f"DISPLAY={self.display} xdotool type --delay 12 -- '{url}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.1)

        await asyncio.create_subprocess_shell(
            f"DISPLAY={self.display} xdotool key Return",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Wait for page to start loading
        await asyncio.sleep(2)
        logger.info("Navigated to %s", url)

    async def restart(self):
        """Kill and restart the browser."""
        logger.info("Restarting Firefox...")
        try:
            proc = await asyncio.create_subprocess_shell(
                "pkill -f firefox-esr",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception:
            pass
        await asyncio.sleep(2)
        await self._launch()

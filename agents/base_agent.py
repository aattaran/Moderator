"""Abstract base class for platform agents."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from config import Settings
from core.playwright_browser import PlaywrightBrowser
from storage.database import Database
from storage.models import Comment, Post

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when an action would exceed rate limits."""


class ApprovalDenied(Exception):
    """Raised when a human reviewer rejects an action."""


class BaseAgent(ABC):
    """Abstract base for all platform agents."""

    def __init__(self, browser: PlaywrightBrowser, db: Database, config: Settings):
        self.browser = browser
        self.db = db
        self.config = config

    @abstractmethod
    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Create and publish a post on the platform."""

    @abstractmethod
    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        """Comment on a target account's post."""

    @abstractmethod
    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        """Scrape engagement metrics from own recent posts."""

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the platform identifier."""

    def _get_daily_post_limit(self) -> int:
        """Get the per-platform daily post limit."""
        platform = self.get_platform_name()
        limits = {
            "facebook": self.config.FACEBOOK_POSTS_PER_DAY,
            "tiktok": self.config.TIKTOK_POSTS_PER_DAY,
        }
        return limits.get(platform, self.config.POSTS_PER_DAY)

    async def check_rate_limit(self, action: str) -> bool:
        """Check if the action is within per-platform rate limits."""
        platform = self.get_platform_name()
        if action == "post":
            count = await self.db.count_posts_today(platform)
            limit = self._get_daily_post_limit()
            if count >= limit:
                raise RateLimitError(
                    f"{platform}: Daily post limit reached: {count}/{limit}"
                )
        elif action == "comment":
            count = await self.db.count_comments_last_hour(platform)
            if count >= self.config.MAX_COMMENTS_PER_HOUR:
                raise RateLimitError(
                    f"{platform}: Hourly comment limit reached: {count}/{self.config.MAX_COMMENTS_PER_HOUR}"
                )
        return True

    async def request_approval(self, content: str, action: str) -> bool:
        """If REQUIRE_APPROVAL is enabled, pause for human review."""
        if not self.config.REQUIRE_APPROVAL:
            return True
        import asyncio
        print(f"\n{'='*60}")
        print(f"[APPROVAL REQUIRED] Action: {action}")
        print(f"Platform: {self.get_platform_name()}")
        print(f"Content:\n{content}")
        print(f"{'='*60}")
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: input("Approve? (y/n): ").strip().lower()
            )
        except EOFError:
            raise ApprovalDenied("No interactive terminal for approval")
        if response != "y":
            raise ApprovalDenied(f"Action '{action}' rejected by reviewer")
        return True

"""Abstract base class for platform agents."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

from config import Settings
from core.computer_use import AgentLoop
from storage.database import Database
from storage.models import Comment, Post

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when an action would exceed rate limits."""


class ApprovalDenied(Exception):
    """Raised when a human reviewer rejects an action."""


class BaseAgent(ABC):
    """Abstract base for all platform agents.

    Each platform agent implements posting, engagement, and metrics
    scraping using the Computer Use agent loop.
    """

    def __init__(
        self,
        agent_loop: AgentLoop,
        db: Database,
        config: Settings,
    ):
        self.agent_loop = agent_loop
        self.db = db
        self.config = config

    @abstractmethod
    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Create and publish a post on the platform."""

    @abstractmethod
    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        """Comment on a target account's post."""

    @abstractmethod
    async def scrape_own_metrics(self) -> list[dict]:
        """Scrape engagement metrics from own recent posts."""

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the platform identifier (e.g., 'x')."""

    async def check_rate_limit(self, action: str) -> bool:
        """Check if the action is within rate limits.

        Raises RateLimitError if limit would be exceeded.
        """
        platform = self.get_platform_name()

        if action == "post":
            count = await self.db.count_posts_today(platform)
            if count >= self.config.MAX_POSTS_PER_DAY:
                raise RateLimitError(
                    f"Daily post limit reached: {count}/{self.config.MAX_POSTS_PER_DAY}"
                )
        elif action == "comment":
            count = await self.db.count_comments_last_hour(platform)
            if count >= self.config.MAX_COMMENTS_PER_HOUR:
                raise RateLimitError(
                    f"Hourly comment limit reached: {count}/{self.config.MAX_COMMENTS_PER_HOUR}"
                )
        return True

    async def request_approval(self, content: str, action: str) -> bool:
        """If REQUIRE_APPROVAL is enabled, pause for human review.

        Returns True if approved (or approval not required).
        Raises ApprovalDenied if rejected.
        """
        if not self.config.REQUIRE_APPROVAL:
            return True

        print(f"\n{'='*60}")
        print(f"[APPROVAL REQUIRED] Action: {action}")
        print(f"Platform: {self.get_platform_name()}")
        print(f"Content:\n{content}")
        print(f"{'='*60}")

        try:
            response = input("Approve? (y/n): ").strip().lower()
        except EOFError:
            raise ApprovalDenied("No interactive terminal for approval")

        if response != "y":
            raise ApprovalDenied(f"Action '{action}' rejected by reviewer")
        return True

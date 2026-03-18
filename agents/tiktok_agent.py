"""TikTok agent — stub for future implementation."""

from agents.base_agent import BaseAgent
from storage.models import Comment, Post


class TikTokAgent(BaseAgent):
    """TikTok platform agent. Not yet implemented."""

    def get_platform_name(self) -> str:
        return "tiktok"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        raise NotImplementedError("TikTok agent not yet implemented")

    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        raise NotImplementedError("TikTok agent not yet implemented")

    async def scrape_own_metrics(self) -> list[dict]:
        raise NotImplementedError("TikTok agent not yet implemented")

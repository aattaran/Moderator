"""Facebook agent — stub for future implementation."""

from agents.base_agent import BaseAgent
from storage.models import Comment, Post


class FacebookAgent(BaseAgent):
    """Facebook platform agent. Not yet implemented."""

    def get_platform_name(self) -> str:
        return "facebook"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        raise NotImplementedError("Facebook agent not yet implemented")

    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        raise NotImplementedError("Facebook agent not yet implemented")

    async def scrape_own_metrics(self) -> list[dict]:
        raise NotImplementedError("Facebook agent not yet implemented")

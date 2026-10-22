"""Facebook Group agent — posting, engagement, and member management via Playwright."""

import logging
from datetime import datetime

from agents.base_agent import BaseAgent
from config import Settings
from core.facebook_actions import FacebookActions
from core.playwright_browser import PlaywrightBrowser
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)


class FacebookAgent(BaseAgent):
    """Facebook Group agent using Playwright browser automation."""

    def __init__(self, browser: PlaywrightBrowser, db: Database, config: Settings):
        super().__init__(browser, db, config)
        self.actions = FacebookActions(browser)

    def get_platform_name(self) -> str:
        return "facebook"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post health content to the Facebook Group."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="facebook", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(
            platform="facebook", content=content,
            content_style=style, topic=topic, status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            success = await self.actions.post_to_group(content)
            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("Posted to Facebook Group (style=%s, topic=%s)", style, topic)
            else:
                await self.db.update_post_status(post.id, "failed")
                post.status = "failed"

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            return post
        except Exception as e:
            await self.db.update_post_status(post.id, "failed")
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def post_with_image(self, content: str, image_path: str, style: str, topic: str) -> Post:
        """Post text + image to the Facebook Group."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="facebook", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(
            platform="facebook", content=content,
            content_style=style, topic=topic, status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            success = await self.actions.post_to_group_with_image(content, image_path)
            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("Posted to Facebook Group with image (style=%s, topic=%s)", style, topic)
            else:
                # Fallback to text-only
                logger.warning("Image post failed, falling back to text-only")
                success = await self.actions.post_to_group(content)
                if success:
                    await self.db.update_post_status(post.id, "posted", datetime.now())
                    post.status = "posted"
                else:
                    await self.db.update_post_status(post.id, "failed")
                    post.status = "failed"

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            return post
        except Exception as e:
            await self.db.update_post_status(post.id, "failed")
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        """Comment on a post in the group."""
        await self.check_rate_limit("comment")

        run = AgentRun(agent="facebook", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="facebook", target_post_url="group_feed",
            target_author=target_username, content=comment_text,
            comment_style=style, topic=topic, status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            import random
            post_index = random.randint(0, 4)
            success = await self.actions.comment_on_group_post(post_index, comment_text)
            if success:
                comment.status = "posted"
                comment.posted_at = datetime.now()

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            return comment
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def approve_members(self, max_count: int = 20) -> int:
        """Approve pending member requests."""
        return await self.actions.approve_pending_members(max_count)

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        return await self.actions.get_group_feed(max_count=10)

"""X (Twitter) agent — posting, engagement, and metrics scraping via Playwright."""

import logging
from datetime import datetime

from agents.base_agent import BaseAgent, RateLimitError
from config import Settings
from core.playwright_browser import PlaywrightBrowser
from core.x_actions import XActions
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)


class XAgent(BaseAgent):
    """X (Twitter) platform agent using Playwright browser automation."""

    def __init__(self, browser: PlaywrightBrowser, db: Database, config: Settings):
        super().__init__(browser, db, config)
        self.actions = XActions(browser)

    def get_platform_name(self) -> str:
        return "x"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post a tweet on X."""
        await self.check_rate_limit("post")
        await self.request_approval(content, "post")

        run = AgentRun(agent="x", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(platform="x", content=content, content_style=style, topic=topic, status="draft")
        post.id = await self.db.insert_post(post)

        try:
            success = await self.actions.compose_and_post(content)

            if success:
                now = datetime.now()
                await self.db.update_post_status(post.id, "posted", now)
                post.status = "posted"
                post.posted_at = now
                logger.info("Posted tweet (style=%s, topic=%s)", style, topic)
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
        """Post a tweet with an attached image."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="x", task_type="post_image", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(platform="x", content=content, content_style=style, topic=topic, status="draft")
        post.id = await self.db.insert_post(post)

        try:
            success = await self.actions.compose_and_post_with_image(content, image_path)

            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("Posted tweet with image (style=%s, topic=%s)", style, topic)
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

    async def post_thread(self, thread_tweets: list[str], style: str, topic: str) -> Post:
        """Post a multi-tweet thread."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="x", task_type="post_thread", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        full_content = "\n---\n".join(thread_tweets)
        post = Post(platform="x", content=full_content, content_style="thread", topic=topic, status="draft")
        post.id = await self.db.insert_post(post)

        try:
            success = await self.actions.compose_and_post_thread(thread_tweets)

            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("Posted thread (%d tweets, topic=%s)", len(thread_tweets), topic)
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
        """Reply to a post on a target account's profile."""
        await self.check_rate_limit("comment")

        run = AgentRun(agent="x", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="x", target_post_url=f"https://x.com/{target_username}",
            target_author=target_username, content=comment_text,
            comment_style=style, topic=topic, status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            success = await self.actions.reply_to_latest_post(target_username, comment_text)

            status = "posted" if success else "failed"
            comment.status = status
            if success:
                comment.posted_at = datetime.now()

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            logger.info("Engagement with @%s: %s (style=%s)", target_username, status, style)
            return comment

        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def like_and_retweet(self, target_username: str, action: str = "like") -> bool:
        """Like and optionally retweet a post."""
        run = AgentRun(agent="x", task_type=f"like_retweet", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            liked = await self.actions.like_latest_post(target_username)
            retweeted = False
            if "retweet" in action and liked:
                retweeted = await self.actions.retweet_latest_post(target_username)

            success = liked
            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            logger.info("Like/retweet @%s: %s (%s)", target_username, "success" if success else "failed", action)
            return success

        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def read_latest_post(self, username: str) -> str:
        """Read the latest post text from a user's profile."""
        return await self.actions.read_latest_post_text(username)

    async def reply_to_mentions(self, max_replies: int = 3, reply_generator=None) -> int:
        """Smart reply to mentions — filters spam, prioritizes quality."""
        run = AgentRun(agent="x", task_type="reply_mentions", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            # Get mentions with metadata
            mentions = await self.actions.get_smart_mentions(max_count=15)

            # Filter: skip empty, very short, or spammy mentions
            quality_mentions = []
            for m in mentions:
                text = m.get("text", "")
                if len(text) < 5:
                    continue  # Too short / empty
                if any(spam in text.lower() for spam in [
                    "dm me", "check my bio", "free", "giveaway", "airdrop",
                    "follow me", "follow back", "f4f", "s4s"
                ]):
                    continue  # Spam
                quality_mentions.append(m)

            # Sort by engagement (likes + replies) — higher quality first
            quality_mentions.sort(key=lambda m: m.get("likes", 0) + m.get("replies", 0), reverse=True)

            replied = 0
            for mention in quality_mentions[:max_replies]:
                if reply_generator:
                    reply_text = await reply_generator(mention["text"])
                else:
                    reply_text = "Thanks for the mention! Great point."

                success = await self.actions.reply_to_mention(mention["element"], reply_text)
                if success:
                    replied += 1
                    logger.info("Replied to @%s (likes=%d)", mention.get("author", "?"), mention.get("likes", 0))

            await self.db.complete_agent_run(run_id, status="success", iterations=1)
            logger.info("Smart replies: %d/%d quality mentions", replied, len(quality_mentions))
            return replied

        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        """Scrape engagement metrics from own recent posts."""
        if not own_username:
            logger.warning("No username provided for metrics scraping")
            return []

        run = AgentRun(agent="x", task_type="scrape", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            metrics = await self.actions.scrape_profile_metrics(own_username)
            await self.db.complete_agent_run(
                run_id, status="success", iterations=1,
            )
            logger.info("Scraped metrics for %d posts", len(metrics))
            return metrics

        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

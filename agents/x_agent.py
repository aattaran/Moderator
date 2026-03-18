"""X (Twitter) agent — posting, engagement, and metrics scraping via Computer Use."""

import json
import logging
from datetime import datetime
from pathlib import Path

from agents.base_agent import BaseAgent, RateLimitError
from config import Settings
from core.computer_use import AgentLoop
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class XAgent(BaseAgent):
    """X (Twitter) platform agent using Claude Computer Use."""

    def get_platform_name(self) -> str:
        return "x"

    def _load_prompt(self, name: str) -> str:
        """Load a system prompt template from the prompts directory."""
        return (PROMPTS_DIR / name).read_text()

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post a tweet on X.

        Args:
            content: The text to post
            style: Content style (e.g., "hot_take", "thread")
            topic: Content topic (e.g., "ai", "tech")

        Returns:
            The created Post record
        """
        await self.check_rate_limit("post")
        await self.request_approval(content, "post")

        # Log the agent run
        run = AgentRun(agent="x", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        # Create the post record (draft)
        post = Post(
            platform="x",
            content=content,
            content_style=style,
            status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            # Load and fill the posting prompt
            system_prompt = self._load_prompt("x_posting.txt")
            task_prompt = system_prompt.replace("{content}", content)
            system_prompt_base = (
                "You are an AI assistant helping a user manage their X (Twitter) account. "
                "You are controlling a web browser via mouse and keyboard actions. "
                "Follow the instructions precisely and report any issues."
            )

            # Run the agent loop
            result = await self.agent_loop.run(
                task=task_prompt,
                system_prompt=system_prompt_base,
                max_iterations=20,
            )

            if result.success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                post.posted_at = datetime.now()
                logger.info("Successfully posted tweet (style=%s, topic=%s)", style, topic)
            else:
                await self.db.update_post_status(post.id, "failed")
                post.status = "failed"
                logger.warning("Post may have failed — agent loop did not complete cleanly")

            await self.db.complete_agent_run(
                run_id,
                status="success" if result.success else "failed",
                iterations=result.iterations,
                api_tokens_used=result.total_input_tokens + result.total_output_tokens,
            )
            return post

        except Exception as e:
            await self.db.update_post_status(post.id, "failed")
            await self.db.complete_agent_run(
                run_id, status="failed", error_message=str(e)
            )
            raise

    async def engage(
        self, target_username: str, comment_text: str, style: str, topic: str
    ) -> Comment:
        """Reply to a post on a target account's profile.

        Args:
            target_username: X username to engage with (without @)
            comment_text: The reply text
            style: Comment style (e.g., "agree_and_extend", "question")
            topic: Topic category (e.g., "ai", "tech")

        Returns:
            The created Comment record
        """
        await self.check_rate_limit("comment")
        await self.request_approval(
            f"Reply to @{target_username}: {comment_text}", "comment"
        )

        run = AgentRun(agent="x", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="x",
            target_post_url=f"https://x.com/{target_username}",
            target_author=target_username,
            content=comment_text,
            comment_style=style,
            topic=topic,
            status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            template = self._load_prompt("x_engagement.txt")
            task_prompt = template.replace(
                "{target_username}", target_username
            ).replace("{comment_text}", comment_text)

            system_prompt_base = (
                "You are an AI assistant helping a user engage on X (Twitter). "
                "You are controlling a web browser via mouse and keyboard actions. "
                "Follow the instructions precisely and report any issues."
            )

            result = await self.agent_loop.run(
                task=task_prompt,
                system_prompt=system_prompt_base,
                max_iterations=25,
            )

            status = "posted" if result.success else "failed"
            comment.status = status
            if result.success:
                comment.posted_at = datetime.now()

            # Update comment in DB (re-insert with status since we don't have update_comment)
            await self.db.complete_agent_run(
                run_id,
                status="success" if result.success else "failed",
                iterations=result.iterations,
                api_tokens_used=result.total_input_tokens + result.total_output_tokens,
            )

            logger.info(
                "Engagement with @%s: %s (style=%s, topic=%s)",
                target_username, status, style, topic,
            )
            return comment

        except Exception as e:
            await self.db.complete_agent_run(
                run_id, status="failed", error_message=str(e)
            )
            raise

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        """Scrape engagement metrics from own recent posts via Computer Use.

        Args:
            own_username: The logged-in user's X username

        Returns:
            List of dicts with post text and engagement counts
        """
        if not own_username:
            logger.warning("No username provided for metrics scraping")
            return []

        run = AgentRun(agent="x", task_type="scrape", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            template = self._load_prompt("x_scraping.txt")
            task_prompt = template.replace("{own_username}", own_username)

            system_prompt_base = (
                "You are an AI assistant helping a user analyze their X (Twitter) metrics. "
                "You are controlling a web browser via mouse and keyboard actions. "
                "Read engagement metrics from posts and report them in JSON format."
            )

            result = await self.agent_loop.run(
                task=task_prompt,
                system_prompt=system_prompt_base,
                max_iterations=15,
            )

            # Parse metrics from Claude's response
            metrics = self._parse_metrics_response(result.final_text)

            await self.db.complete_agent_run(
                run_id,
                status="success",
                iterations=result.iterations,
                api_tokens_used=result.total_input_tokens + result.total_output_tokens,
            )

            logger.info("Scraped metrics for %d posts", len(metrics))
            return metrics

        except Exception as e:
            await self.db.complete_agent_run(
                run_id, status="failed", error_message=str(e)
            )
            raise

    @staticmethod
    def _parse_metrics_response(text: str) -> list[dict]:
        """Extract JSON metrics from Claude's text response."""
        # Look for JSON array in the response
        try:
            # Find the JSON block (may be wrapped in ```json ... ```)
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse metrics JSON: %s", e)
        return []

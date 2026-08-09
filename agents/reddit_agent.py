"""Reddit agent — karma building and MCRO promotion via PRAW API."""

import asyncio
import logging
import random
from datetime import datetime, timedelta

from agents.base_agent import BaseAgent
from config import Settings
from core.reddit_actions import RedditActions
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)


class RedditAgent(BaseAgent):
    """Reddit agent using PRAW (official Python Reddit API)."""

    def __init__(self, db: Database, config: Settings):
        super().__init__(None, db, config)
        self.reddit = RedditActions(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            username=config.REDDIT_USERNAME,
            password=config.REDDIT_PASSWORD,
            user_agent=config.REDDIT_USER_AGENT or f"Moderator:v1.0 (by /u/{config.REDDIT_USERNAME})",
        )
        self._karma_cache: dict | None = None
        self._karma_cache_time: datetime | None = None

    async def start(self):
        success = await asyncio.to_thread(self.reddit.login)
        if not success:
            raise RuntimeError("Reddit: failed to login via PRAW")
        logger.info("Reddit agent started (PRAW)")

    async def stop(self):
        pass  # PRAW has no persistent session to save

    def get_platform_name(self) -> str:
        return "reddit"

    # ── Karma phase logic ─────────────────────────────────────

    async def get_karma(self) -> dict:
        """Get current karma, cached for 1 hour."""
        now = datetime.now()
        if self._karma_cache and self._karma_cache_time and (now - self._karma_cache_time).total_seconds() < 3600:
            return self._karma_cache
        self._karma_cache = await asyncio.to_thread(self.reddit.get_karma)
        self._karma_cache_time = now
        return self._karma_cache

    async def get_karma_phase(self) -> str:
        """Determine posting phase based on karma.
        - comment_only (0-50): only comment, no posts
        - comment_and_post (50-200): can post to less restrictive subs
        - full (200+): full posting, soft promotion allowed
        """
        karma = await self.get_karma()
        total = karma["total_karma"]
        if total < 50:
            return "comment_only"
        elif total < 200:
            return "comment_and_post"
        return "full"

    async def should_promote(self) -> bool:
        """Check 10:1 ratio — at least 10 non-promotional actions per 1 promotional."""
        counts = await self.db.count_promotional_actions("reddit", days=30)
        total = counts["total"]
        promotional = counts["promotional"]
        non_promotional = counts["non_promotional"]

        if total == 0:
            return False  # Need some history first
        if promotional == 0:
            return non_promotional >= 10  # Need at least 10 non-promo before first promo
        return non_promotional / max(promotional, 1) >= 10

    # ── Core agent methods ────────────────────────────────────

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post to a subreddit. Content should be 'title\\n---\\nbody' format."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="reddit", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        # Parse title and body from content
        if "\n---\n" in content:
            title, body = content.split("\n---\n", 1)
        else:
            lines = content.split("\n", 1)
            title = lines[0]
            body = lines[1] if len(lines) > 1 else ""

        post = Post(
            platform="reddit", content=content,
            content_style=style, topic=topic, status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            # Select subreddit using strategy (weighted random, not first-match)
            from strategies.reddit_content_strategy import RedditContentStrategy, CONTENT_TYPES
            strategy = RedditContentStrategy(None, self.db)
            karma = await self.get_karma()
            total_karma = karma["total_karma"]

            result_sub = strategy.select_subreddit_for_post(total_karma)
            subreddit = result_sub[0] if result_sub else "SideProject"

            is_promo = CONTENT_TYPES.get(style, {}).get("promotional", False)

            # Enforce 10:1 ratio before promotional posts
            if is_promo and not await self.should_promote():
                logger.info("Reddit: 10:1 ratio not met — skipping promotional post")
                await self.db.update_post_status(post.id, "failed")
                post.status = "skipped"
                await self.db.complete_agent_run(run_id, status="success", iterations=0)
                return post

            result = await asyncio.to_thread(
                self.reddit.submit_text_post, subreddit, title.strip(), body.strip()
            )

            if result:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("Reddit post to r/%s: %s", subreddit, result.get("url"))
            else:
                await self.db.update_post_status(post.id, "failed")
                post.status = "failed"

            await self.db.complete_agent_run(
                run_id, status="success" if result else "failed", iterations=1,
            )
            return post
        except Exception as e:
            await self.db.update_post_status(post.id, "failed")
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        """Comment on a Reddit post. target_username is the submission ID."""
        await self.check_rate_limit("comment")

        run = AgentRun(agent="reddit", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="reddit",
            target_post_url=f"https://reddit.com/comments/{target_username}",
            target_author=target_username,
            content=comment_text,
            comment_style=style, topic=topic, status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            result = await asyncio.to_thread(
                self.reddit.comment_on_submission, target_username, comment_text,
            )

            if result:
                comment.status = "posted"
                comment.posted_at = datetime.now()
                logger.info("Reddit comment on %s in r/%s", target_username, result.get("subreddit"))
            else:
                comment.status = "failed"

            await self.db.complete_agent_run(
                run_id, status="success" if result else "failed", iterations=1,
            )
            return comment
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        """Scrape karma metrics."""
        run = AgentRun(agent="reddit", task_type="scrape", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            karma = await asyncio.to_thread(self.reddit.get_karma)
            # Log to karma table
            await self.db.insert_reddit_karma(
                karma["username"], karma["comment_karma"],
                karma["link_karma"], karma["total_karma"],
            )
            await self.db.complete_agent_run(run_id, status="success", iterations=1)
            logger.info(
                "Reddit karma: comment=%d, link=%d, total=%d",
                karma["comment_karma"], karma["link_karma"], karma["total_karma"],
            )
            return [karma]
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    # ── Comment cycle — find relevant posts and comment ───────

    async def find_and_comment(self, max_comments: int = 3) -> int:
        """Scan subreddits for relevant posts and comment helpfully."""
        from strategies.reddit_content_strategy import RedditContentStrategy, SUBREDDIT_CONFIG

        strategy = RedditContentStrategy(None, self.db)
        commented = 0

        for _ in range(max_comments):
            subreddit = strategy.select_subreddit_for_comment()
            config = SUBREDDIT_CONFIG.get(subreddit, {})

            # Get recent posts
            posts = await asyncio.to_thread(self.reddit.get_hot_posts, subreddit, 20)
            if not posts:
                continue

            # Filter for relevance
            relevant = [p for p in posts if strategy.is_post_relevant(p, subreddit)]
            if not relevant:
                # Try new posts instead
                posts = await asyncio.to_thread(self.reddit.get_new_posts, subreddit, 15)
                relevant = [p for p in posts if strategy.is_post_relevant(p, subreddit)]

            if not relevant:
                continue

            # Pick a post (prefer fewer comments = more visibility)
            relevant.sort(key=lambda p: p["num_comments"])
            post = relevant[0]

            # Determine comment type
            phase = await self.get_karma_phase()
            can_promote = phase == "full" and await self.should_promote()
            if can_promote and "tool_mention_comment" in config.get("comment_types", []):
                content_type = "tool_mention_comment"
            else:
                content_type = random.choice(["helpful_comment", "experience_share"])

            # Generate comment
            comment_text = await strategy.generate_comment(
                post["title"], post["body"], subreddit, content_type,
            )

            # Post it
            result = await self.engage(
                post["id"], comment_text, content_type, "reddit_engagement",
            )

            if result.status == "posted":
                commented += 1
                logger.info("Reddit: commented on '%s' in r/%s", post["title"][:50], subreddit)

            # Wait between comments
            await asyncio.sleep(random.uniform(60, 180))

        return commented

"""Top-level orchestrator — wires everything together and coordinates agent tasks."""

import asyncio
import logging
import random
from datetime import datetime

from agents.base_agent import RateLimitError
from agents.x_agent import XAgent
from analytics.analyzer import EngagementAnalyzer
from analytics.feedback_loop import FeedbackLoop
from analytics.scraper import MetricsScraper
from config import Settings
from core.browser import BrowserSession
from core.computer_use import AgentLoop
from storage.database import Database
from strategies.content_strategy import ContentStrategy
from strategies.engagement_strategy import EngagementStrategy
from strategies.targeting_strategy import TargetingStrategy
from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Top-level coordinator for all agent operations.

    Wires together: database, agent loop, weight manager, strategies,
    and platform agents. Provides high-level methods for each task type.
    """

    def __init__(self, config: Settings):
        self.config = config
        self.db = Database(config.DB_PATH)
        self.agent_loop = AgentLoop(
            api_key=config.ANTHROPIC_API_KEY,
            model=config.MODEL,
            display_width=config.DISPLAY_WIDTH,
            display_height=config.DISPLAY_HEIGHT,
            dry_run=config.DRY_RUN,
        )
        self.weight_manager = WeightManager(self.db, config)
        self.content_strategy = ContentStrategy(self.weight_manager)
        self.engagement_strategy = EngagementStrategy(self.weight_manager)
        self.targeting_strategy = TargetingStrategy(self.db)

        # Create the platform agent
        self.agent = XAgent(self.agent_loop, self.db, config)

        # Analytics
        self.scraper = MetricsScraper(self.db, self.agent)
        self.analyzer = EngagementAnalyzer(self.db)
        self.feedback_loop = FeedbackLoop(self.scraper, self.weight_manager)

        # Browser session
        self.browser = BrowserSession(config.BROWSER_PROFILE_PATH)

    async def initialize(self):
        """Initialize database and seed default weights."""
        await self.db.initialize()
        await self.weight_manager.initialize_defaults()
        logger.info("Orchestrator initialized")

    async def execute_post(self):
        """Execute a single posting task."""
        logger.info("Executing post task...")
        async with self.browser:
            try:
                # Generate content
                content_prompt, style, topic = (
                    await self.content_strategy.generate_post_prompt()
                )
                content = await self.content_strategy.generate_content_text(style, topic)

                # Post it
                post = await self.agent.post_content(content, style, topic)
                logger.info("Posted successfully: id=%s, style=%s, topic=%s", post.id, style, topic)

            except RateLimitError as e:
                logger.warning("Skipping post: %s", e)
            except Exception as e:
                logger.error("Post task failed: %s", e, exc_info=True)

    async def execute_engagement_cycle(self):
        """Execute one engagement cycle — multiple comments on target accounts."""
        logger.info("Starting engagement cycle (%d comments)...", self.config.COMMENTS_PER_CYCLE)
        platform = self.agent.get_platform_name()

        async with self.browser:
            for i in range(self.config.COMMENTS_PER_CYCLE):
                try:
                    # Select target
                    target = await self.targeting_strategy.select_target(platform)
                    if not target:
                        logger.warning("No targets available, ending cycle")
                        break

                    # Generate comment
                    comment_prompt, style, topic = (
                        await self.engagement_strategy.generate_comment_prompt()
                    )
                    comment_text = await self.engagement_strategy.generate_comment_text(
                        style, topic
                    )

                    # Post the comment
                    comment = await self.agent.engage(
                        target.username, comment_text, style, topic
                    )
                    logger.info(
                        "Comment %d/%d: @%s (style=%s)",
                        i + 1, self.config.COMMENTS_PER_CYCLE,
                        target.username, style,
                    )

                    # Random delay between comments (30-120 seconds)
                    if i < self.config.COMMENTS_PER_CYCLE - 1:
                        delay = random.uniform(30, 120)
                        logger.debug("Waiting %.0f seconds before next comment", delay)
                        await asyncio.sleep(delay)

                except RateLimitError as e:
                    logger.warning("Rate limit reached: %s", e)
                    break
                except Exception as e:
                    logger.error("Engagement failed for comment %d: %s", i + 1, e)

    async def execute_metrics_scrape(self, own_username: str = ""):
        """Scrape engagement metrics from own posts."""
        logger.info("Scraping metrics...")
        async with self.browser:
            try:
                updated = await self.scraper.scrape_post_metrics(own_username)
                logger.info("Updated metrics for %d posts", updated)
            except Exception as e:
                logger.error("Metrics scrape failed: %s", e, exc_info=True)

    async def evaluate_weights(self):
        """Run weight evaluation (no scraping, uses existing data)."""
        platform = self.agent.get_platform_name()
        await self.feedback_loop.run_weight_evaluation_only(platform)

    async def get_status(self) -> dict:
        """Get current system status for the CLI."""
        platform = self.agent.get_platform_name()
        recent_runs = await self.db.get_recent_runs(limit=10)
        recent_posts = await self.db.get_recent_posts(platform, limit=5)

        weights = {}
        for category in ["content_style", "comment_style", "topic"]:
            weights[category] = await self.weight_manager.get_weights_summary(category)

        return {
            "platform": platform,
            "dry_run": self.config.DRY_RUN,
            "require_approval": self.config.REQUIRE_APPROVAL,
            "recent_runs": [
                {
                    "agent": r.agent,
                    "task": r.task_type,
                    "status": r.status,
                    "started": str(r.started_at),
                    "iterations": r.iterations,
                    "tokens": r.api_tokens_used,
                }
                for r in recent_runs
            ],
            "recent_posts": [
                {
                    "id": p.id,
                    "style": p.content_style,
                    "status": p.status,
                    "likes": p.engagement_likes,
                    "content": p.content[:80] + "..." if len(p.content) > 80 else p.content,
                }
                for p in recent_posts
            ],
            "weights": weights,
        }

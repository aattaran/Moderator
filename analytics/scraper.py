"""Engagement metrics scraper — uses Computer Use to read metrics from platforms."""

import logging
from datetime import datetime

from agents.x_agent import XAgent
from storage.database import Database

logger = logging.getLogger(__name__)


class MetricsScraper:
    """Scrapes engagement metrics from social media platforms via Computer Use."""

    def __init__(self, db: Database, agent: XAgent):
        self.db = db
        self.agent = agent

    async def scrape_post_metrics(self, own_username: str) -> int:
        """Scrape metrics for recent posts and update the database.

        Returns the number of posts updated.
        """
        metrics = await self.agent.scrape_own_metrics(own_username)
        if not metrics:
            logger.info("No metrics scraped")
            return 0

        # Match scraped metrics to posts in the database
        platform = self.agent.get_platform_name()
        recent_posts = await self.db.get_recent_posts(platform, limit=20)
        updated = 0

        for post in recent_posts:
            if post.status != "posted" or not post.id:
                continue

            # Try to match by content prefix
            for metric in metrics:
                scraped_text = metric.get("text", "")
                if scraped_text and post.content[:50] in scraped_text:
                    await self.db.update_post_engagement(
                        post.id,
                        likes=metric.get("likes", 0),
                        reposts=metric.get("reposts", 0),
                        replies=metric.get("replies", 0),
                        views=metric.get("views", 0),
                    )
                    updated += 1
                    break

        logger.info("Updated metrics for %d/%d posts", updated, len(recent_posts))
        return updated

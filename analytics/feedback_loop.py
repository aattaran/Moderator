"""Feedback loop — connects analytics to the adaptive weight system."""

import logging

from analytics.scraper import MetricsScraper
from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Runs the analytics → weight adjustment cycle.

    This is the core learning mechanism:
    1. Scrape latest engagement metrics
    2. Evaluate each weight category
    3. Adjust weights based on performance
    """

    def __init__(self, scraper: MetricsScraper, weight_manager: WeightManager):
        self.scraper = scraper
        self.weight_manager = weight_manager

    async def run_full_cycle(self, platform: str, own_username: str):
        """Run a complete feedback cycle: scrape → analyze → adjust weights."""
        logger.info("Starting feedback loop cycle for %s", platform)

        # 1. Scrape latest metrics
        updated = await self.scraper.scrape_post_metrics(own_username)
        logger.info("Updated metrics for %d posts", updated)

        # 2. Evaluate and adjust weights for each category
        for category in ["content_style", "comment_style", "topic"]:
            logger.info("Evaluating weights for %s", category)
            await self.weight_manager.evaluate_period(category, platform)

        # 3. Log new weight state
        for category in ["content_style", "comment_style", "topic"]:
            weights = await self.weight_manager.get_weights_summary(category)
            logger.info("Current %s weights: %s", category, weights)

        logger.info("Feedback loop cycle complete")

    async def run_weight_evaluation_only(self, platform: str):
        """Run weight evaluation without scraping (uses existing data)."""
        for category in ["content_style", "comment_style", "topic"]:
            await self.weight_manager.evaluate_period(category, platform)
            weights = await self.weight_manager.get_weights_summary(category)
            logger.info("Updated %s weights: %s", category, weights)

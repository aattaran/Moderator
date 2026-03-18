"""Adaptive weight scoring system for content and engagement strategies."""

import logging
import random
from datetime import datetime, timedelta

from config import Settings
from storage.database import Database
from storage.models import WeightEntry

logger = logging.getLogger(__name__)

# Default options for each category
DEFAULT_CONTENT_STYLES = ["hot_take", "thread", "question", "insight", "meme_caption"]
DEFAULT_COMMENT_STYLES = [
    "agree_and_extend", "question", "humor", "counterpoint", "resource_share"
]
DEFAULT_TOPICS = ["ai", "tech", "startups", "culture", "science"]

MIN_SAMPLES_FOR_ADJUSTMENT = 3


class WeightManager:
    """Manages adaptive weights for content styles, comment styles, and topics.

    Each option starts at weight 1.0. Over time, weights are adjusted based
    on engagement performance — higher-performing options get higher weight
    (more likely to be selected), while lower-performing options get lower
    weight but never drop below the floor.
    """

    def __init__(self, db: Database, config: Settings):
        self.db = db
        self.config = config

    async def initialize_defaults(self):
        """Seed default weights for all categories if none exist."""
        now = datetime.now()
        await self.db.initialize_weights("content_style", DEFAULT_CONTENT_STYLES, now)
        await self.db.initialize_weights("comment_style", DEFAULT_COMMENT_STYLES, now)
        await self.db.initialize_weights("topic", DEFAULT_TOPICS, now)

    async def select(self, category: str) -> str:
        """Select an option from a category using weighted random sampling.

        Higher-weighted options are more likely to be selected, but all
        options have a chance (minimum weight floor prevents zero probability).
        """
        entries = await self.db.get_current_weights(category)
        if not entries:
            # Fallback to defaults if DB is empty
            defaults = self._get_defaults(category)
            return random.choice(defaults)

        names = [e.name for e in entries]
        weights = [e.weight for e in entries]
        return random.choices(names, weights=weights, k=1)[0]

    async def evaluate_period(self, category: str, platform: str):
        """Evaluate engagement and adjust weights for a category.

        This should be called periodically (e.g., every WEIGHT_EVAL_PERIOD_DAYS).

        Algorithm:
        1. For each option, compute average engagement during the period
        2. Compare each option's average to the overall category average
        3. Adjust: new_weight = old_weight + LEARNING_RATE * (option_avg - overall_avg) / overall_avg
        4. Floor: enforce MIN_WEIGHT_FLOOR
        5. Normalize: scale so weights sum to len(options)
        """
        entries = await self.db.get_current_weights(category)
        if not entries:
            return

        period_start = datetime.now() - timedelta(days=self.config.WEIGHT_EVAL_PERIOD_DAYS)
        period_end = datetime.now()

        # Compute average engagement per option
        engagements: dict[str, float] = {}
        for entry in entries:
            avg = await self._get_avg_engagement(
                category, entry.name, platform, period_start, period_end
            )
            if avg is not None:
                engagements[entry.name] = avg

        if len(engagements) < 2:
            logger.info(
                "Not enough data for %s evaluation (%d options with data)",
                category, len(engagements),
            )
            return

        overall_avg = sum(engagements.values()) / len(engagements)
        if overall_avg == 0:
            logger.info("Overall average engagement is 0 for %s, skipping", category)
            return

        # Adjust weights
        for entry in entries:
            if entry.name not in engagements:
                continue  # Not enough samples, carry forward

            delta = self.config.LEARNING_RATE * (
                (engagements[entry.name] - overall_avg) / overall_avg
            )
            old_weight = entry.weight
            entry.weight = max(self.config.MIN_WEIGHT_FLOOR, entry.weight + delta)

            logger.info(
                "Weight %s/%s: %.3f → %.3f (avg_engagement=%.1f, overall=%.1f)",
                category, entry.name, old_weight, entry.weight,
                engagements[entry.name], overall_avg,
            )

        # Normalize so weights sum to len(entries), then enforce floor
        total = sum(e.weight for e in entries)
        target_sum = len(entries)
        if total > 0:
            # Iteratively normalize and enforce floor until stable
            for _ in range(5):
                cur_total = sum(e.weight for e in entries)
                for entry in entries:
                    entry.weight = entry.weight * target_sum / cur_total
                for entry in entries:
                    entry.weight = max(self.config.MIN_WEIGHT_FLOOR, entry.weight)
            for entry in entries:
                entry.sample_count = 0  # Reset for next period
                entry.avg_engagement = engagements.get(entry.name, 0)
                await self.db.upsert_weight_entry(entry)

        logger.info("Weight evaluation complete for %s", category)

    async def _get_avg_engagement(
        self, category: str, name: str, platform: str,
        since: datetime, until: datetime
    ) -> float | None:
        """Get average engagement for an option in a category.

        Returns None if fewer than MIN_SAMPLES_FOR_ADJUSTMENT samples exist.
        """
        if category == "content_style":
            posts = await self.db.get_posts_by_style(platform, name, since, until)
            if len(posts) < MIN_SAMPLES_FOR_ADJUSTMENT:
                return None
            total = sum(
                p.engagement_likes + p.engagement_reposts + p.engagement_replies
                for p in posts
            )
            return total / len(posts) if posts else 0

        elif category == "comment_style":
            comments = await self.db.get_comments_by_style(platform, name, since, until)
            if len(comments) < MIN_SAMPLES_FOR_ADJUSTMENT:
                return None
            total = sum(c.engagement_likes + c.engagement_replies for c in comments)
            return total / len(comments) if comments else 0

        elif category == "topic":
            comments = await self.db.get_comments_by_topic(platform, name, since, until)
            if len(comments) < MIN_SAMPLES_FOR_ADJUSTMENT:
                return None
            total = sum(c.engagement_likes + c.engagement_replies for c in comments)
            return total / len(comments) if comments else 0

        return None

    async def get_weights_summary(self, category: str) -> dict[str, float]:
        """Return current weights as a name→weight dict for display."""
        entries = await self.db.get_current_weights(category)
        return {e.name: round(e.weight, 3) for e in entries}

    @staticmethod
    def _get_defaults(category: str) -> list[str]:
        if category == "content_style":
            return DEFAULT_CONTENT_STYLES
        elif category == "comment_style":
            return DEFAULT_COMMENT_STYLES
        elif category == "topic":
            return DEFAULT_TOPICS
        return []

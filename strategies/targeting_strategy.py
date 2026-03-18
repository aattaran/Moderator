"""Targeting strategy — finds high-value accounts to engage with."""

import logging
import random

from storage.database import Database
from storage.models import TargetAccount

logger = logging.getLogger(__name__)


class TargetingStrategy:
    """Selects target accounts for engagement based on scoring."""

    def __init__(self, db: Database):
        self.db = db

    async def select_target(self, platform: str) -> TargetAccount | None:
        """Select a target account for engagement using weighted random selection.

        Accounts are scored by: follower_count * engagement_rate * relevance_score.
        Higher-scored accounts are more likely to be selected.
        """
        accounts = await self.db.get_active_targets(platform, limit=50)
        if not accounts:
            logger.warning("No active target accounts for %s", platform)
            return None

        # Score each account
        scored = []
        for account in accounts:
            score = max(
                account.follower_count * account.avg_engagement_rate * account.relevance_score,
                0.01,  # Minimum score so all accounts have a chance
            )
            scored.append((account, score))

        # Weighted random selection
        accounts_list = [a for a, _ in scored]
        weights = [s for _, s in scored]
        selected = random.choices(accounts_list, weights=weights, k=1)[0]

        logger.info(
            "Selected target: @%s (followers=%d, engagement=%.3f, relevance=%.2f)",
            selected.username,
            selected.follower_count,
            selected.avg_engagement_rate,
            selected.relevance_score,
        )
        return selected

    async def add_target(
        self,
        platform: str,
        username: str,
        follower_count: int = 0,
        engagement_rate: float = 0.0,
        relevance_score: float = 0.5,
    ) -> int:
        """Add or update a target account."""
        from datetime import datetime

        account = TargetAccount(
            platform=platform,
            username=username,
            follower_count=follower_count,
            avg_engagement_rate=engagement_rate,
            relevance_score=relevance_score,
            last_checked=datetime.now(),
        )
        return await self.db.upsert_target_account(account)

"""Engagement analysis — aggregates trends and computes insights."""

import logging
from datetime import datetime, timedelta

from storage.database import Database
from strategies.weight_manager import DEFAULT_CONTENT_STYLES, DEFAULT_TOPICS

logger = logging.getLogger(__name__)


class EngagementAnalyzer:
    """Analyzes engagement data to identify trends and optimal strategies."""

    def __init__(self, db: Database):
        self.db = db

    async def get_style_performance(
        self, platform: str, days: int = 30
    ) -> dict[str, dict]:
        """Get engagement performance breakdown by content style.

        Returns dict of style → {count, avg_likes, avg_reposts, avg_replies, avg_views}.
        """
        since = datetime.now() - timedelta(days=days)
        until = datetime.now()
        results = {}

        for style in DEFAULT_CONTENT_STYLES:
            posts = await self.db.get_posts_by_style(platform, style, since, until)
            if not posts:
                results[style] = {
                    "count": 0, "avg_likes": 0, "avg_reposts": 0,
                    "avg_replies": 0, "avg_views": 0,
                }
                continue

            results[style] = {
                "count": len(posts),
                "avg_likes": sum(p.engagement_likes for p in posts) / len(posts),
                "avg_reposts": sum(p.engagement_reposts for p in posts) / len(posts),
                "avg_replies": sum(p.engagement_replies for p in posts) / len(posts),
                "avg_views": sum(p.engagement_views for p in posts) / len(posts),
            }

        return results

    async def get_topic_performance(
        self, platform: str, days: int = 30
    ) -> dict[str, dict]:
        """Get engagement performance breakdown by topic."""
        since = datetime.now() - timedelta(days=days)
        until = datetime.now()
        results = {}

        for topic in DEFAULT_TOPICS:
            comments = await self.db.get_comments_by_topic(platform, topic, since, until)
            if not comments:
                results[topic] = {"count": 0, "avg_likes": 0, "avg_replies": 0}
                continue

            results[topic] = {
                "count": len(comments),
                "avg_likes": sum(c.engagement_likes for c in comments) / len(comments),
                "avg_replies": sum(c.engagement_replies for c in comments) / len(comments),
            }

        return results

    async def generate_summary(self, platform: str) -> str:
        """Generate a human-readable analytics summary."""
        style_perf = await self.get_style_performance(platform)
        topic_perf = await self.get_topic_performance(platform)

        lines = ["=== Engagement Summary (Last 30 Days) ===", ""]
        lines.append("Content Styles:")
        for style, data in sorted(
            style_perf.items(), key=lambda x: x[1]["avg_likes"], reverse=True
        ):
            if data["count"] > 0:
                lines.append(
                    f"  {style}: {data['count']} posts, "
                    f"avg {data['avg_likes']:.0f} likes, "
                    f"{data['avg_reposts']:.0f} reposts, "
                    f"{data['avg_replies']:.0f} replies"
                )

        lines.append("")
        lines.append("Comment Topics:")
        for topic, data in sorted(
            topic_perf.items(), key=lambda x: x[1]["avg_likes"], reverse=True
        ):
            if data["count"] > 0:
                lines.append(
                    f"  {topic}: {data['count']} comments, "
                    f"avg {data['avg_likes']:.0f} likes, "
                    f"{data['avg_replies']:.0f} replies"
                )

        return "\n".join(lines)

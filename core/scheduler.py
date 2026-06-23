"""Task scheduler for automated posting, engagement, and analytics cycles."""

import logging
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import Settings

logger = logging.getLogger(__name__)


class TaskScheduler:
    """APScheduler-based scheduler for recurring agent tasks.

    Post type is selected dynamically at runtime via weight_manager,
    not statically at schedule time.
    """

    def __init__(self, config: Settings):
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self._callbacks = {}

    def set_callbacks(self, **kwargs):
        self._callbacks = kwargs

    def setup(self):
        """Configure all scheduled tasks."""
        posts_per_day = self.config.POSTS_PER_DAY
        waking_hours = list(range(8, 23))

        # X (Twitter) jobs are gated on PLATFORMS. When "x" is NOT in PLATFORMS, none
        # of the X posting/engagement/like/reply/discovery/scrape/reflection jobs are
        # scheduled at all — a hard structural guard so a paused X account cannot be
        # posted to until X is deliberately re-enabled via PLATFORMS.
        x_enabled = "x" in [p.strip() for p in self.config.PLATFORMS.split(",")]

        if x_enabled:
            # Schedule N posts — type chosen dynamically at runtime by smart_post_callback
            post_hours = sorted(random.sample(waking_hours, min(posts_per_day, len(waking_hours))))
            for i, hour in enumerate(post_hours):
                minute = random.randint(0, 59)
                self.scheduler.add_job(
                    self._safe_run("smart_post_callback", "smart_post"),
                    CronTrigger(hour=hour, minute=minute),
                    id=f"post_{i}", name=f"Post at {hour}:{minute:02d}",
                    jitter=900,
                )
                logger.info("Scheduled post #%d at %d:%02d", i + 1, hour, minute)

            # Engagement cycles (comments) every N hours
            self.scheduler.add_job(
                self._safe_run("engage_callback", "engage"),
                IntervalTrigger(hours=self.config.ENGAGEMENT_CYCLE_INTERVAL_HOURS),
                id="engagement", name="Engagement cycle (comments)",
                jitter=600,
            )

            # Like cycle every 8 hours (reduced — likes don't drive engagement back)
            self.scheduler.add_job(
                self._safe_run("like_retweet_callback", "like_retweet"),
                IntervalTrigger(hours=8),
                id="like_retweet", name="Like cycle",
                jitter=600,
            )

            # Reply to mentions every 4 hours
            self.scheduler.add_job(
                self._safe_run("reply_mentions_callback", "reply_mentions"),
                IntervalTrigger(hours=4),
                id="reply_mentions", name="Reply to mentions",
                jitter=600,
            )

            # Discovery cycle every 6 hours — find new accounts, evaluate existing ones
            self.scheduler.add_job(
                self._safe_run("discovery_callback", "discovery"),
                IntervalTrigger(hours=6),
                id="discovery", name="Account discovery & evaluation",
                jitter=900,
            )

            # Metrics scraping every N hours (scrapes own X posts)
            self.scheduler.add_job(
                self._safe_run("scrape_callback", "scrape"),
                IntervalTrigger(hours=self.config.ANALYTICS_SCRAPE_INTERVAL_HOURS),
                id="metrics_scrape", name="Metrics scraping",
            )

            # Content reflection every 3 days at 5 AM (X persona)
            self.scheduler.add_job(
                self._safe_run("reflection_callback", "content_reflection"),
                CronTrigger(day="*/3", hour=5, minute=0),
                id="content_reflection", name="Content reflection & guideline update",
            )
        else:
            logger.warning("X disabled (not in PLATFORMS) — skipping all X post/engage/scrape jobs")

        # Weight evaluation daily at 4 AM (platform-agnostic)
        self.scheduler.add_job(
            self._safe_run("evaluate_callback", "evaluate"),
            CronTrigger(hour=4, minute=0),
            id="weight_eval", name="Weight evaluation",
        )

        # Facebook Group posts (3/day at random hours)
        fb_hours = sorted(random.sample(list(range(9, 21)), min(3, 12)))
        for i, hour in enumerate(fb_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run("facebook_post_callback", "facebook_post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"fb_post_{i}", name=f"Facebook post at {hour}:{minute:02d}",
                jitter=900,
            )

        # Facebook engagement every 4 hours
        self.scheduler.add_job(
            self._safe_run("facebook_engage_callback", "facebook_engage"),
            IntervalTrigger(hours=4),
            id="fb_engage", name="Facebook Group engagement",
            jitter=600,
        )

        # Facebook member approval every 6 hours
        self.scheduler.add_job(
            self._safe_run("facebook_approve_callback", "facebook_approve"),
            IntervalTrigger(hours=6),
            id="fb_approve", name="Facebook member approval",
            jitter=600,
        )

        # Media sync from DO Spaces every 2 hours
        self.scheduler.add_job(
            self._safe_run("media_sync_callback", "media_sync"),
            IntervalTrigger(hours=2),
            id="media_sync", name="Media sync from Spaces",
        )

        # ELEMNT content reflection every 3 days at 5:30 AM
        self.scheduler.add_job(
            self._safe_run("elemnt_reflection_callback", "elemnt_reflection"),
            CronTrigger(day="*/3", hour=5, minute=30),
            id="elemnt_reflection", name="ELEMNT content reflection",
        )

        # Instagram posts (2/day)
        ig_hours = sorted(random.sample(list(range(10, 20)), 2))
        for i, hour in enumerate(ig_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run("instagram_post_callback", "instagram_post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"ig_post_{i}", name=f"Instagram post at {hour}:{minute:02d}",
                jitter=900,
            )

        # TikTok posts (2/day at peak hours 6pm-10pm)
        tt_hours = sorted(random.sample([18, 19, 20, 21], 2))
        for i, hour in enumerate(tt_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run("tiktok_post_callback", "tiktok_post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"tt_post_{i}", name=f"TikTok post at {hour}:{minute:02d}",
                jitter=900,
            )

        # YouTube Shorts (2/day at midday)
        yt_hours = sorted(random.sample([11, 12, 13, 14, 15, 16], 2))
        for i, hour in enumerate(yt_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run("youtube_post_callback", "youtube_post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"yt_post_{i}", name=f"YouTube Short at {hour}:{minute:02d}",
                jitter=900,
            )

        # Reddit comment cycle every 2 hours
        self.scheduler.add_job(
            self._safe_run("reddit_comment_callback", "reddit_comment"),
            IntervalTrigger(hours=2),
            id="reddit_comment", name="Reddit comment cycle",
            jitter=600,
        )

        # Reddit posts (2/day at peak Reddit hours: 9-10am, 6-8pm EST = 14-15, 23-01 UTC)
        reddit_hours = sorted(random.sample([9, 10, 14, 18, 19, 20], 2))
        for i, hour in enumerate(reddit_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run("reddit_post_callback", "reddit_post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"reddit_post_{i}", name=f"Reddit post at {hour}:{minute:02d}",
                jitter=900,
            )

        # Reddit karma tracking every 12 hours
        self.scheduler.add_job(
            self._safe_run("reddit_karma_callback", "reddit_karma"),
            IntervalTrigger(hours=12),
            id="reddit_karma", name="Reddit karma tracking",
        )

        # Campaign reply monitor every 30 minutes
        self.scheduler.add_job(
            self._safe_run("campaign_monitor_callback", "campaign_monitor"),
            IntervalTrigger(minutes=30),
            id="campaign_monitor", name="Campaign reply monitor",
            jitter=300,
        )

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self.scheduler.get_jobs()))

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def get_next_runs(self) -> list[dict]:
        jobs = self.scheduler.get_jobs()
        return [
            {"id": job.id, "name": job.name,
             "next_run": str(job.next_run_time) if job.next_run_time else "N/A"}
            for job in jobs
        ]

    def _safe_run(self, callback_key: str, task_name: str):
        async def wrapper():
            callback = self._callbacks.get(callback_key)
            try:
                if callback:
                    await callback()
                else:
                    logger.warning("No callback for '%s'", callback_key)
            except Exception as e:
                logger.error("Task '%s' failed: %s", task_name, e, exc_info=True)
        return wrapper

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

    Schedules:
    - N posts/day at randomized optimal hours with jitter
    - Engagement cycles every N hours
    - Metrics scraping daily
    - Weight evaluation daily
    """

    def __init__(self, config: Settings):
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self._post_callback = None
        self._engage_callback = None
        self._scrape_callback = None
        self._evaluate_callback = None

    def set_callbacks(
        self,
        post_callback,
        engage_callback,
        scrape_callback,
        evaluate_callback,
    ):
        """Set the async callback functions for each task type."""
        self._post_callback = post_callback
        self._engage_callback = engage_callback
        self._scrape_callback = scrape_callback
        self._evaluate_callback = evaluate_callback

    def setup(self):
        """Configure all scheduled tasks."""
        # Posts: distribute N posts across waking hours (8 AM - 10 PM)
        waking_hours = list(range(8, 22))
        post_hours = sorted(random.sample(waking_hours, min(self.config.POSTS_PER_DAY, len(waking_hours))))

        for i, hour in enumerate(post_hours):
            minute = random.randint(0, 59)
            self.scheduler.add_job(
                self._safe_run(self._post_callback, "post"),
                CronTrigger(hour=hour, minute=minute),
                id=f"post_{i}",
                name=f"Post #{i+1} at {hour}:{minute:02d}",
                jitter=900,  # ±15 minutes randomization
            )
            logger.info("Scheduled post #%d at %d:%02d (±15min)", i + 1, hour, minute)

        # Engagement cycles every N hours
        self.scheduler.add_job(
            self._safe_run(self._engage_callback, "engage"),
            IntervalTrigger(hours=self.config.ENGAGEMENT_CYCLE_INTERVAL_HOURS),
            id="engagement",
            name="Engagement cycle",
            jitter=600,  # ±10 minutes
        )

        # Metrics scraping daily at 3 AM
        self.scheduler.add_job(
            self._safe_run(self._scrape_callback, "scrape"),
            CronTrigger(hour=3, minute=0),
            id="metrics_scrape",
            name="Metrics scraping",
        )

        # Weight evaluation daily at 4 AM
        self.scheduler.add_job(
            self._safe_run(self._evaluate_callback, "evaluate"),
            CronTrigger(hour=4, minute=0),
            id="weight_eval",
            name="Weight evaluation",
        )

    def start(self):
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self.scheduler.get_jobs()))

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def get_next_runs(self) -> list[dict]:
        """Get info about upcoming scheduled tasks."""
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
            }
            for job in jobs
        ]

    @staticmethod
    def _safe_run(callback, task_name: str):
        """Wrap a callback with error handling so scheduler doesn't crash."""
        async def wrapper():
            try:
                if callback:
                    await callback()
            except Exception as e:
                logger.error("Scheduled task '%s' failed: %s", task_name, e, exc_info=True)
        return wrapper

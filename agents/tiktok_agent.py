"""TikTok agent — video posting and engagement via Playwright."""

import glob
import logging
import os
from datetime import datetime

from agents.base_agent import BaseAgent
from config import Settings
from core.tiktok_actions import TikTokActions
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)

PRODUCT_VIDEOS_DIR = "data/product_videos"


class TikTokAgent(BaseAgent):
    """TikTok agent using Playwright browser automation."""

    def __init__(self, db: Database, config: Settings):
        super().__init__(None, db, config)
        # Sticky residential session (same IP for 24h), mirroring the Instagram agent.
        # Distinct session id so TikTok and Instagram don't share one exit IP.
        proxy_password = ""
        if config.PROXY_SERVER and config.PROXY_PASSWORD:
            proxy_password = f"{config.PROXY_PASSWORD}_country-us_session-tiktok1_lifetime-24h"
        self.tt_actions = TikTokActions(
            auth_state_file="data/tiktok_auth_state.json",
            proxy_server=config.PROXY_SERVER,
            proxy_username=config.PROXY_USERNAME,
            proxy_password=proxy_password,
        )

    async def start(self):
        await self.tt_actions.start()

    async def stop(self):
        await self.tt_actions.stop()

    def get_platform_name(self) -> str:
        return "tiktok"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post a video with health caption to TikTok."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="tiktok", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        # Choose the video before inserting, so the filename is recorded on the row —
        # that record IS the post-once ledger read back by _pick_next_video.
        video_path = await self._pick_next_video()

        post = Post(
            platform="tiktok", content=content,
            content_style=style, topic=topic, status="draft",
            media_urls=[os.path.basename(video_path)] if video_path else [],
        )
        post.id = await self.db.insert_post(post)

        try:
            if not video_path:
                logger.error("No videos found in %s", PRODUCT_VIDEOS_DIR)
                await self.db.update_post_status(post.id, "failed")
                await self.db.complete_agent_run(run_id, status="failed", error_message="No videos")
                post.status = "failed"
                return post

            logger.info("TikTok: selected %s", os.path.basename(video_path))
            success = await self.tt_actions.post_video(video_path, content)

            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("TikTok post: style=%s, topic=%s", style, topic)
            else:
                await self.db.update_post_status(post.id, "failed")
                post.status = "failed"

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            return post
        except Exception as e:
            await self.db.update_post_status(post.id, "failed")
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def engage(self, target_username: str, comment_text: str, style: str, topic: str) -> Comment:
        """Comment on a TikTok video."""
        await self.check_rate_limit("comment")

        run = AgentRun(agent="tiktok", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="tiktok", target_post_url="foryou",
            target_author=target_username, content=comment_text,
            comment_style=style, topic=topic, status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            success = await self.tt_actions.comment_on_video(comment_text)
            if success:
                comment.status = "posted"
                comment.posted_at = datetime.now()

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            return comment
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        return []

    async def _pick_next_video(self) -> str | None:
        """Pick the next video, posting every file once before repeating any.

        Ordered by: never-posted first, then operator-tagged good/great takes, then
        filename. Once the library is exhausted the same ordering falls through to
        least-recently-posted, so a long-running account cycles instead of sticking
        on one file. Replaces a random pick that could repeat a video the same week
        while leaving others never posted.
        """
        videos = glob.glob(os.path.join(PRODUCT_VIDEOS_DIR, "*.mp4"))
        if not videos:
            return None

        last_posted = await self.db.get_media_last_posted("tiktok")

        def sort_key(path: str):
            name = os.path.basename(path)
            lowered = name.lower()
            preferred = 0 if ("good" in lowered or "great" in lowered) else 1
            # "" sorts before any timestamp, so never-posted files come first.
            return (last_posted.get(name, ""), preferred, name)

        ordered = sorted(videos, key=sort_key)
        unposted = [v for v in videos if os.path.basename(v) not in last_posted]
        logger.info(
            "TikTok: %d/%d videos never posted", len(unposted), len(videos)
        )
        return ordered[0]

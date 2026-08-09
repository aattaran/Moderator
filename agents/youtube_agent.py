"""YouTube Shorts agent — uploads health videos via YouTube Data API v3."""

import glob
import logging
import os
import random
from datetime import datetime

from agents.base_agent import BaseAgent
from config import Settings
from core.youtube_actions import YouTubeActions
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)

PRODUCT_VIDEOS_DIR = "data/product_videos"


class YouTubeAgent(BaseAgent):
    """YouTube Shorts agent using the official Data API."""

    def __init__(self, db: Database, config: Settings):
        super().__init__(None, db, config)
        self.yt = YouTubeActions(
            client_secrets_file=getattr(config, "YOUTUBE_CLIENT_SECRETS_FILE", "data/youtube_client_secrets.json"),
            credentials_file=getattr(config, "YOUTUBE_CREDENTIALS_FILE", "data/youtube_credentials.json"),
        )

    async def start(self):
        if not self.yt.is_authenticated():
            logger.warning("YouTube: not authenticated — run: python scripts/youtube_auth.py")

    async def stop(self):
        pass

    def get_platform_name(self) -> str:
        return "youtube"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Upload a product video as a YouTube Short with health caption."""
        await self.check_rate_limit("post")

        # Pick video first so media_urls is populated on insert (enables dedup)
        video_path = await self._pick_random_video()
        if not video_path:
            logger.info("YouTube: no videos available in %s — agent done draining backlog", PRODUCT_VIDEOS_DIR)
            post = Post(
                platform="youtube", content=content,
                content_style=style, topic=topic, status="failed",
            )
            post.id = await self.db.insert_post(post)
            return post

        run = AgentRun(agent="youtube", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(
            platform="youtube", content=content,
            content_style=style, topic=topic, status="draft",
            media_urls=[os.path.basename(video_path)],
        )
        post.id = await self.db.insert_post(post)

        try:
            # Generate title from first sentence of content
            title = content.split(".")[0].strip()
            if len(title) > 90:
                title = title[:87] + "..."

            # Tags from topic
            tags = ["supplements", "health", "Shorts"]
            if topic:
                tags.append(topic.replace("_", " "))

            result = self.yt.upload_short(
                video_path=video_path,
                title=title,
                description=content,
                tags=tags,
            )

            if result:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info("YouTube Short posted: %s", result.get("url", ""))
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
        raise NotImplementedError("YouTube commenting not yet implemented")

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        return []

    async def _get_posted_videos(self) -> set[str]:
        """Get filenames of videos already posted to YouTube."""
        posts = await self.db.get_recent_posts("youtube", limit=100)
        posted = set()
        for p in posts:
            for url in (p.media_urls or []):
                posted.add(os.path.basename(url))
        return posted

    async def _pick_random_video(self) -> str | None:
        videos = glob.glob(os.path.join(PRODUCT_VIDEOS_DIR, "*.mp4"))
        posted = await self._get_posted_videos()
        available = [v for v in videos if os.path.basename(v) not in posted]
        if not available:
            return None
        good = [v for v in available if "good" in os.path.basename(v).lower()]
        return random.choice(good) if good else random.choice(available)

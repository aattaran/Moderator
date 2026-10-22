"""Instagram agent — posting images/videos and engagement via instagrapi mobile API."""

import glob
import logging
import os
import random
from datetime import datetime

from agents.base_agent import BaseAgent
from config import Settings
from core.instagram_actions import InstagrapiActions
from storage.database import Database
from storage.models import AgentRun, Comment, Post

logger = logging.getLogger(__name__)

# Paths to existing ELEMNT product assets
PRODUCT_IMAGES_DIR = "data/product_images"
PRODUCT_VIDEOS_DIR = "data/product_videos"


class InstagramAgent(BaseAgent):
    """Instagram agent using instagrapi mobile API (i.instagram.com)."""

    def __init__(self, db: Database, config: Settings):
        # Instagram doesn't use the shared Playwright browser
        super().__init__(None, db, config)
        # Build proxy URL with sticky session (same IP for 24h)
        proxy = ""
        if config.PROXY_SERVER:
            host = config.PROXY_SERVER.replace("http://", "").replace("https://", "")
            user = config.PROXY_USERNAME
            pwd = f"{config.PROXY_PASSWORD}_country-us_session-elemnt1_lifetime-24h"
            proxy = f"http://{user}:{pwd}@{host}"
        self.ig = InstagrapiActions(
            proxy=proxy,
            username=getattr(config, "IG_USERNAME", ""),
            password=getattr(config, "IG_PASSWORD", ""),
            switch_to=getattr(config, "IG_SWITCH_TO", ""),
        )

    async def start(self):
        """Login to Instagram via sessionid."""
        success = self.ig.login()
        if not success:
            raise RuntimeError("Instagram: failed to login via sessionid")
        logger.info("Instagram agent started (instagrapi)")

    async def stop(self):
        """Save session state on shutdown."""
        self.ig.save_session()
        logger.info("Instagram agent stopped, session saved")

    def get_platform_name(self) -> str:
        return "instagram"

    async def post_content(self, content: str, style: str, topic: str) -> Post:
        """Post health content with a product image to Instagram."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="instagram", task_type="post", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(
            platform="instagram", content=content,
            content_style=style, topic=topic, status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            # 80% chance: generate UGC influencer image, 20%: use existing product image
            image_path = None
            if random.random() < 0.8:
                try:
                    from media.ugc_image_generator import UGCImageGenerator
                    ugc = UGCImageGenerator(api_key=self.config.GEMINI_API_KEY)
                    image_path = str(await ugc.generate_for_platform(topic=topic, platform="instagram"))
                    logger.info("Instagram: using AI-generated UGC image")
                except Exception as e:
                    logger.warning("Instagram: UGC generation failed, falling back to product image: %s", e)

            if not image_path:
                image_path = self._pick_random_image()

            if not image_path:
                logger.error("No product images found in %s", PRODUCT_IMAGES_DIR)
                await self.db.update_post_status(post.id, "failed")
                await self.db.complete_agent_run(run_id, status="failed", error_message="No images")
                post.status = "failed"
                return post

            result = self.ig.post_image(image_path, content)
            success = result is not None

            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info(
                    "Instagram post: style=%s, topic=%s, media_id=%s",
                    style, topic, result.get("media_id"),
                )
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

    async def post_video(self, caption: str, style: str, topic: str) -> Post:
        """Post a product video (Reel) to Instagram."""
        await self.check_rate_limit("post")

        run = AgentRun(agent="instagram", task_type="post_video", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        post = Post(
            platform="instagram", content=caption,
            content_style=style, topic=topic, status="draft",
        )
        post.id = await self.db.insert_post(post)

        try:
            posted = await self._get_posted_videos()
            video_path = self._pick_random_video(posted_filenames=posted)
            if not video_path:
                logger.error("No product videos found in %s", PRODUCT_VIDEOS_DIR)
                await self.db.update_post_status(post.id, "failed")
                await self.db.complete_agent_run(run_id, status="failed", error_message="No videos")
                post.status = "failed"
                return post

            # Store video filename in media_urls for dedup tracking
            post.media_urls = [video_path]

            result = self.ig.post_video(video_path, caption)
            success = result is not None

            if success:
                await self.db.update_post_status(post.id, "posted", datetime.now())
                post.status = "posted"
                logger.info(
                    "Instagram video post: style=%s, topic=%s, media_id=%s",
                    style, topic, result.get("media_id"),
                )
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
        """Like and comment on a target user's latest post."""
        await self.check_rate_limit("comment")

        run = AgentRun(agent="instagram", task_type="engage", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        comment = Comment(
            platform="instagram", target_post_url=f"https://instagram.com/{target_username}",
            target_author=target_username, content=comment_text,
            comment_style=style, topic=topic, status="draft",
        )
        comment.id = await self.db.insert_comment(comment)

        try:
            # Get the target user's latest media
            medias = self.ig.get_user_media(target_username, amount=3)
            if not medias:
                logger.warning("Instagram: no media found for @%s", target_username)
                await self.db.complete_agent_run(
                    run_id, status="failed", iterations=1,
                    error_message=f"No media for @{target_username}",
                )
                comment.status = "failed"
                return comment

            target_media = random.choice(medias)
            media_id = target_media.id

            # Like the post
            self.ig.like_post(media_id)

            # Comment on the post
            success = self.ig.comment_on_post(media_id, comment_text)

            if success:
                comment.status = "posted"
                comment.posted_at = datetime.now()

            await self.db.complete_agent_run(
                run_id, status="success" if success else "failed", iterations=1,
            )
            logger.info(
                "Instagram engagement with @%s: %s (style=%s)",
                target_username, comment.status, style,
            )
            return comment
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    async def scrape_own_metrics(self, own_username: str = "") -> list[dict]:
        """Scrape engagement metrics from own recent posts via API."""
        if not own_username:
            logger.warning("No username provided for Instagram metrics scraping")
            return []

        run = AgentRun(agent="instagram", task_type="scrape", started_at=datetime.now())
        run_id = await self.db.log_agent_run(run)

        try:
            medias = self.ig.get_user_media(own_username, amount=20)
            metrics = []
            for m in medias:
                metrics.append({
                    "media_id": str(m.id),
                    "code": m.code,
                    "caption": (m.caption_text or "")[:200],
                    "likes": m.like_count,
                    "comments": m.comment_count,
                    "media_type": str(m.media_type),
                    "taken_at": str(m.taken_at) if m.taken_at else None,
                })
            await self.db.complete_agent_run(run_id, status="success", iterations=1)
            logger.info("Instagram: scraped metrics for %d posts", len(metrics))
            return metrics
        except Exception as e:
            await self.db.complete_agent_run(run_id, status="failed", error_message=str(e))
            raise

    def _pick_random_image(self) -> str | None:
        """Pick a product image (excluding already-resized _ig files), resize to Instagram format."""
        patterns = [f"{PRODUCT_IMAGES_DIR}/**/*.jpg", f"{PRODUCT_IMAGES_DIR}/**/*.png"]
        images = []
        for p in patterns:
            images.extend(glob.glob(p, recursive=True))
        # Exclude previously resized files to prevent quality degradation and _ig_ig accumulation
        images = [i for i in images if "_ig." not in os.path.basename(i)]
        if not images:
            return None
        image_path = random.choice(images)
        return self._resize_for_instagram(image_path)

    def _resize_for_instagram(self, image_path: str) -> str:
        """Resize/crop image to Instagram 4:5 portrait (1080x1350). Saves to data/tmp/."""
        try:
            import tempfile
            from PIL import Image
            img = Image.open(image_path)
            target_w, target_h = 1080, 1350
            target_ratio = target_w / target_h

            w, h = img.size
            current_ratio = w / h

            if current_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            elif current_ratio < target_ratio:
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))

            img = img.resize((target_w, target_h), Image.LANCZOS)

            # Save to a temp dir — never overwrite source images
            tmp_dir = os.path.join("data", "tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            ext = ".jpg" if image_path.lower().endswith(".jpg") else ".png"
            resized_path = os.path.join(tmp_dir, f"ig_{os.path.splitext(os.path.basename(image_path))[0]}{ext}")
            img.save(resized_path, quality=95)
            logger.info("Resized for Instagram: %s → %dx%d", os.path.basename(image_path), target_w, target_h)
            return resized_path
        except Exception as e:
            logger.warning("Failed to resize image: %s, using original", e)
            return image_path

    async def _get_posted_videos(self) -> set[str]:
        """Get filenames of videos already posted to avoid duplicates."""
        posts = await self.db.get_recent_posts("instagram", limit=100)
        posted = set()
        for p in posts:
            if p.media_urls:
                for url in p.media_urls:
                    basename = os.path.basename(url)
                    if basename:
                        posted.add(basename)
        return posted

    def _pick_random_video(self, posted_filenames: set[str] | None = None) -> str | None:
        """Pick a video that hasn't been posted yet. No duplicates."""
        patterns = [f"{PRODUCT_VIDEOS_DIR}/**/*.mp4"]
        videos = []
        for p in patterns:
            videos.extend(glob.glob(p, recursive=True))

        if not videos:
            return None

        # Filter out already-posted videos
        if posted_filenames:
            available = [v for v in videos if os.path.basename(v) not in posted_filenames]
            if not available:
                logger.warning("All %d videos already posted — resetting pool", len(videos))
                available = videos  # Reset if all used
        else:
            available = videos

        # Prefer "good_" prefixed videos
        good = [v for v in available if "good" in os.path.basename(v).lower()]
        return random.choice(good) if good else random.choice(available)

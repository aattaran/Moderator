"""Top-level orchestrator — wires everything together and coordinates agent tasks."""

import asyncio
import logging
import random
from datetime import datetime

from agents.base_agent import RateLimitError
from agents.x_agent import XAgent
from analytics.analyzer import EngagementAnalyzer
from analytics.feedback_loop import FeedbackLoop
from analytics.scraper import MetricsScraper
from config import Settings
from core.playwright_browser import PlaywrightBrowser
from storage.database import Database
from core.freebie_campaign import FreebieCampaignManager
from strategies.content_reflector import ContentReflector
from strategies.content_strategy import ContentStrategy
from strategies.engagement_strategy import EngagementStrategy
from strategies.targeting_strategy import TargetingStrategy
from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Top-level coordinator for all agent operations."""

    def __init__(self, config: Settings):
        self.config = config
        self.db = Database(config.DB_PATH)
        # X browser — no proxy needed, X.com works from datacenter IPs
        self.browser = PlaywrightBrowser(
            user_data_dir=config.BROWSER_PROFILE_PATH,
            headless=not config.ENABLE_VNC,
        )
        self.weight_manager = WeightManager(self.db, config)
        self.content_strategy = ContentStrategy(self.weight_manager, db=self.db)
        self.engagement_strategy = EngagementStrategy(self.weight_manager)
        self.content_reflector = ContentReflector(self.db, config)
        self.targeting_strategy = TargetingStrategy(self.db)

        # Multi-platform agents
        self.agents = {}
        platforms = config.PLATFORMS.split(",")

        if "x" in platforms:
            self.agents["x"] = XAgent(self.browser, self.db, config)

        if "instagram" in platforms:
            from agents.instagram_agent import InstagramAgent
            self.agents["instagram"] = InstagramAgent(self.db, config)

        if "tiktok" in platforms:
            from agents.tiktok_agent import TikTokAgent
            self.agents["tiktok"] = TikTokAgent(self.db, config)

        if "youtube" in platforms:
            from agents.youtube_agent import YouTubeAgent
            self.agents["youtube"] = YouTubeAgent(self.db, config)

        if "reddit" in platforms:
            from agents.reddit_agent import RedditAgent
            self.agents["reddit"] = RedditAgent(self.db, config)

        if "facebook" in platforms:
            from agents.facebook_agent import FacebookAgent
            # Facebook browser — no proxy needed, works from datacenter IPs
            self._fb_browser = PlaywrightBrowser(
                user_data_dir=config.BROWSER_PROFILE_PATH,
                headless=not config.ENABLE_VNC,
                auth_state_file="data/facebook_auth_state.json",
            )
            self.agents["facebook"] = FacebookAgent(self._fb_browser, self.db, config)

        # Default to X agent for backwards compatibility
        self.agent = self.agents.get("x")

        self.campaign_manager = FreebieCampaignManager(
            self.db, self.agents["x"].actions if "x" in self.agents else None, config
        ) if "x" in self.agents else None
        self.scraper = MetricsScraper(self.db, self.agent) if self.agent else None
        self.analyzer = EngagementAnalyzer(self.db)
        self.feedback_loop = FeedbackLoop(self.scraper, self.weight_manager)

        self._image_gen = None

    def _get_image_generator(self):
        if self._image_gen is None:
            from media.image_generator import ImageGenerator
            self._image_gen = ImageGenerator(
                api_key=self.config.GEMINI_API_KEY,
                output_dir=__import__("pathlib").Path("data/media"),
            )
        return self._image_gen

    async def initialize(self):
        await self.db.initialize()
        await self.weight_manager.initialize_defaults()

        from strategies.seed_guidelines import seed_initial_guidelines
        await seed_initial_guidelines(self.db)

        try:
            await self.browser.start()
        except Exception as e:
            logger.error("X browser failed to start (disabling X): %s", e)
            self.agents.pop("x", None)
            self.agent = None

        # Start platform-specific agents — each wrapped so one failure doesn't kill the rest
        failed_platforms = []
        for platform in ["instagram", "tiktok", "youtube", "reddit"]:
            if platform in self.agents:
                try:
                    await self.agents[platform].start()
                except Exception as e:
                    logger.error("%s agent failed to start (disabling): %s", platform, e)
                    failed_platforms.append(platform)

        if hasattr(self, '_fb_browser'):
            try:
                await self._fb_browser.start()
            except Exception as e:
                logger.error("Facebook browser failed to start (disabling): %s", e)
                failed_platforms.append("facebook")

        # Remove failed platforms so the scheduler doesn't try to use them
        for platform in failed_platforms:
            self.agents.pop(platform, None)

        logger.info("Orchestrator initialized (platforms: %s)", list(self.agents.keys()))
        if failed_platforms:
            logger.warning("Disabled platforms: %s", failed_platforms)

    async def shutdown(self):
        await self.browser.stop()

    # ── Smart posting — type chosen by learned weights ───────────

    async def execute_smart_post(self):
        """Pick post type (text/image/thread) using learned weights, then execute."""
        post_type = await self.weight_manager.select("post_type")
        logger.info("Smart post selected type: %s", post_type)

        if post_type == "image":
            await self.execute_image_post()
        elif post_type == "thread":
            await self.execute_thread()
        else:
            await self.execute_post()

    async def execute_post(self):
        """Post a single text tweet."""
        logger.info("Executing text post...")
        try:
            # Check for trending topics first
            trending = await self._get_trending_topics()
            _, style, topic = await self.content_strategy.generate_post_prompt(trending_topics=trending)
            content = await self.content_strategy.generate_content_text(style, topic)
            post = await self.agent.post_content(content, style, topic)
            logger.info("Posted: id=%s, style=%s, topic=%s", post.id, style, topic)
        except RateLimitError as e:
            logger.warning("Skipping post: %s", e)
        except Exception as e:
            logger.error("Post task failed: %s", e, exc_info=True)

    async def execute_image_post(self):
        """Generate an image and post a tweet with it."""
        logger.info("Executing image post...")
        try:
            trending = await self._get_trending_topics()
            _, style, topic = await self.content_strategy.generate_post_prompt(trending_topics=trending)
            content = await self.content_strategy.generate_content_text(style, topic)

            image_gen = self._get_image_generator()
            image_prompt = f"A visually striking illustration for a social media post about: {content[:100]}"
            image_path = await image_gen.generate_image(image_prompt, style=style)

            post = await self.agent.post_with_image(content, str(image_path), style, topic)
            logger.info("Image post: id=%s, style=%s", post.id, style)
        except RateLimitError as e:
            logger.warning("Skipping image post: %s", e)
        except Exception as e:
            logger.error("Image post failed: %s", e, exc_info=True)

    async def execute_thread(self):
        """Generate and post a multi-tweet thread."""
        logger.info("Executing thread...")
        try:
            trending = await self._get_trending_topics()
            _, style, topic = await self.content_strategy.generate_post_prompt(trending_topics=trending)
            thread_tweets = await self.content_strategy.generate_thread(topic)
            post = await self.agent.post_thread(thread_tweets, style, topic)
            logger.info("Thread: id=%s, %d tweets", post.id, len(thread_tweets))
        except RateLimitError as e:
            logger.warning("Skipping thread: %s", e)
        except Exception as e:
            logger.error("Thread failed: %s", e, exc_info=True)

    # ── Context-aware engagement ─────────────────────────────────

    async def execute_engagement_cycle(self):
        """Execute engagement cycle — reads target post before commenting."""
        logger.info("Starting engagement cycle (%d comments)...", self.config.COMMENTS_PER_CYCLE)
        platform = self.agent.get_platform_name()

        for i in range(self.config.COMMENTS_PER_CYCLE):
            try:
                target = await self.targeting_strategy.select_target(platform)
                if not target:
                    logger.warning("No targets available")
                    break

                # Read the target's latest post for context
                post_context = await self.agent.read_latest_post(target.username)
                logger.info("Read post from @%s: %s", target.username, post_context[:80] if post_context else "none")

                # Skip political content
                from strategies.targeting_strategy import is_political
                if post_context and is_political(post_context):
                    logger.info("Skipping @%s — political content detected", target.username)
                    continue

                _, style, topic = await self.engagement_strategy.generate_comment_prompt()
                comment_text = await self.engagement_strategy.generate_comment_text(
                    style, topic, post_context=post_context
                )
                await self.agent.engage(target.username, comment_text, style, topic)
                logger.info("Comment %d/%d: @%s", i + 1, self.config.COMMENTS_PER_CYCLE, target.username)

                if i < self.config.COMMENTS_PER_CYCLE - 1:
                    await asyncio.sleep(random.uniform(30, 120))

            except RateLimitError as e:
                logger.warning("Rate limit: %s", e)
                break
            except Exception as e:
                logger.error("Engagement failed: %s", e)

    async def execute_like_retweet_cycle(self):
        logger.info("Starting like cycle (no retweets)...")
        from strategies.targeting_strategy import is_political
        platform = self.agent.get_platform_name()
        targets = await self.targeting_strategy.get_all_targets(platform)
        if not targets:
            return

        # Reduced: 1-2 targets, like only (retweets just boost others' content)
        selected = random.sample(targets, min(random.randint(1, 2), len(targets)))
        for target in selected:
            try:
                # Read bio + latest post, skip if political
                context = await self.agent.actions.read_profile_context(target.username)
                if is_political(context):
                    logger.info("Skipping like @%s — political content detected", target.username)
                    continue
                await self.agent.like_and_retweet(target.username, "like")
                await asyncio.sleep(random.uniform(15, 60))
            except Exception as e:
                logger.error("Like @%s: %s", target.username, e)

    async def execute_reply_to_mentions(self):
        """Smart reply to mentions — filters spam, prioritizes quality."""
        logger.info("Checking mentions (smart filtering)...")
        try:
            replied = await self.agent.reply_to_mentions(
                max_replies=3,
                reply_generator=self.engagement_strategy.generate_mention_reply,
            )
            logger.info("Replied to %d mentions", replied)
        except Exception as e:
            logger.error("Reply to mentions failed: %s", e, exc_info=True)

    # ── Trend scraping ───────────────────────────────────────────

    async def _get_trending_topics(self) -> list[str]:
        """Scrape trending topics from X's Explore/Trending page."""
        try:
            from core.x_actions import XActions
            actions = XActions(self.browser)
            trends = await actions.get_trending_topics()
            if trends:
                logger.info("Trending: %s", ", ".join(trends[:5]))
            return trends
        except Exception as e:
            logger.debug("Could not fetch trends: %s", e)
            return []

    # ── Discovery & target management ──────────────────────────

    async def execute_discovery_cycle(self):
        """Discover new accounts from feed and trending, evaluate existing targets."""
        logger.info("Starting discovery cycle...")
        platform = self.agent.get_platform_name()

        try:
            from core.x_actions import XActions
            actions = XActions(self.browser)

            # Discover from feed
            feed_accounts = await actions.discover_accounts_from_feed(max_count=15)
            await self.targeting_strategy.ingest_discovered_accounts(platform, feed_accounts)

            # Discover from trending
            trending_accounts = await actions.discover_accounts_from_trending(max_count=10)
            await self.targeting_strategy.ingest_discovered_accounts(platform, trending_accounts)

            # Evaluate existing targets — boost winners, prune losers
            await self.targeting_strategy.evaluate_targets(platform)

            targets = await self.targeting_strategy.get_all_targets(platform)
            logger.info("Discovery complete. Active targets: %d", len(targets))

        except Exception as e:
            logger.error("Discovery cycle failed: %s", e, exc_info=True)

    # ── Analytics ────────────────────────────────────────────────

    async def execute_metrics_scrape(self, own_username: str = ""):
        logger.info("Scraping metrics...")
        try:
            updated = await self.scraper.scrape_post_metrics(own_username)
            logger.info("Updated metrics for %d posts", updated)
        except Exception as e:
            logger.error("Metrics scrape failed: %s", e, exc_info=True)

    async def evaluate_weights(self):
        platform = self.agent.get_platform_name()
        await self.feedback_loop.run_weight_evaluation_only(platform)

    async def execute_content_reflection(self):
        """Run content reflection for X — analyze posts and update style guidelines."""
        guideline = await self.content_reflector.run_reflection("x")
        if guideline:
            logger.info("X guidelines v%d — %d posts analyzed", guideline.version, guideline.posts_analyzed)
        else:
            logger.info("X reflection skipped (not enough data)")

    async def execute_elemnt_reflection(self):
        """Run content reflection for ELEMNT health platforms."""
        for platform in ["facebook", "instagram"]:
            if platform not in self.agents:
                continue
            guideline = await self.content_reflector.run_reflection(platform)
            if guideline:
                logger.info(
                    "ELEMNT guidelines v%d (%s) — %d posts analyzed",
                    guideline.version, platform, guideline.posts_analyzed,
                )
            else:
                logger.info("ELEMNT reflection skipped for %s (not enough data)", platform)

    # ── Facebook Group ─────────────────────────────────────────

    async def execute_facebook_post(self):
        """Post health content to the Facebook Group."""
        fb_agent = self.agents.get("facebook")
        if not fb_agent:
            return

        logger.info("Posting to Facebook Group...")
        try:
            from strategies.elemnt_content_strategy import ElemntContentStrategy
            elemnt = ElemntContentStrategy(self.weight_manager, self.db)
            content, style, topic = await elemnt.generate_post(platform="facebook")

            # 80% chance: post with AI-generated UGC image
            import random
            if random.random() < 0.8:
                try:
                    from media.ugc_image_generator import UGCImageGenerator
                    ugc = UGCImageGenerator(api_key=self.config.GEMINI_API_KEY)
                    image_path = str(await ugc.generate_for_platform(topic=topic, platform="facebook"))
                    post = await fb_agent.post_with_image(content, image_path, style, topic)
                    logger.info("Facebook image post: id=%s, style=%s", post.id, style)
                    return
                except Exception as e:
                    logger.warning("UGC generation failed, posting text only: %s", e)

            post = await fb_agent.post_content(content, style, topic)
            logger.info("Facebook post: id=%s, style=%s, topic=%s", post.id, style, topic)
        except Exception as e:
            logger.error("Facebook post failed: %s", e, exc_info=True)

    async def execute_facebook_engage(self):
        """Comment on group posts with health-related content."""
        fb_agent = self.agents.get("facebook")
        if not fb_agent:
            return

        logger.info("Engaging in Facebook Group...")
        try:
            from strategies.elemnt_content_strategy import ElemntContentStrategy
            elemnt = ElemntContentStrategy(self.weight_manager, self.db)
            content, style, topic = await elemnt.generate_post(platform="facebook")
            # Use as a comment on a recent post
            await fb_agent.engage("group_member", content, style, topic)
        except Exception as e:
            logger.error("Facebook engagement failed: %s", e)

    async def execute_facebook_approve_members(self):
        """Approve pending member requests."""
        fb_agent = self.agents.get("facebook")
        if not fb_agent:
            return
        try:
            approved = await fb_agent.approve_members(max_count=20)
            logger.info("Approved %d Facebook Group members", approved)
        except Exception as e:
            logger.error("Facebook member approval failed: %s", e)

    # ── Media sync ────────────────────────────────────────────

    async def execute_media_sync(self):
        """Pull new videos/images from DigitalOcean Spaces."""
        try:
            from scripts.sync_media import sync_media
            downloaded = sync_media()
            if downloaded > 0:
                logger.info("Media sync: %d new files downloaded", downloaded)
        except Exception as e:
            logger.error("Media sync failed: %s", e)

    # ── Instagram ─────────────────────────────────────────────

    async def execute_instagram_post(self):
        """Post ELEMNT content with product image to Instagram."""
        ig_agent = self.agents.get("instagram")
        if not ig_agent:
            return

        logger.info("Posting to Instagram...")
        try:
            from strategies.elemnt_content_strategy import ElemntContentStrategy
            elemnt = ElemntContentStrategy(self.weight_manager, self.db)
            content, style, topic = await elemnt.generate_post(platform="instagram")

            # 20% UGC video, 10% pre-made video, 70% UGC image
            import random
            roll = random.random()
            if roll < 0.2 and self.config.KLING_ACCESS_KEY_ID:
                try:
                    from media.ugc_video_generator import UGCVideoGenerator
                    vg = UGCVideoGenerator(
                        gemini_api_key=self.config.GEMINI_API_KEY,
                        kling_access_key=self.config.KLING_ACCESS_KEY_ID,
                        kling_secret_key=self.config.KLING_SECRET_KEY,
                        fal_api_key=self.config.FAL_API_KEY,
                        db=self.db,
                    )
                    video_path = str(await vg.generate(
                        topic=topic,
                        platform="instagram",
                        clip_count=self.config.UGC_CLIP_COUNT,
                        clip_duration=self.config.UGC_CLIP_DURATION,
                        actor_dir=self.config.UGC_ACTOR_DIR,
                        scene_image=self.config.UGC_SCENE_IMAGE,
                        actor_gender=self.config.UGC_ACTOR_GENDER,
                    ))
                    post = await ig_agent.post_video(video_path, style, topic)
                    logger.info("Instagram UGC video: id=%s, style=%s", post.id, style)
                    return
                except Exception as e:
                    logger.warning("UGC video failed, falling back to image: %s", e)
            elif roll < 0.3:
                post = await ig_agent.post_video(content, style, topic)
                logger.info("Instagram video: id=%s, style=%s", post.id, style)
            else:
                post = await ig_agent.post_content(content, style, topic)
                logger.info("Instagram image: id=%s, style=%s", post.id, style)
        except Exception as e:
            logger.error("Instagram post failed: %s", e, exc_info=True)

    # ── TikTok ────────────────────────────────────────────────

    async def execute_tiktok_post(self):
        """Post ELEMNT video to TikTok."""
        tt_agent = self.agents.get("tiktok")
        if not tt_agent:
            return

        logger.info("Posting to TikTok...")
        try:
            from strategies.elemnt_content_strategy import ElemntContentStrategy
            elemnt = ElemntContentStrategy(self.weight_manager, self.db)
            content, style, topic = await elemnt.generate_post(platform="tiktok")
            post = await tt_agent.post_content(content, style, topic)
            logger.info("TikTok post: id=%s, style=%s", post.id, style)
        except Exception as e:
            logger.error("TikTok post failed: %s", e, exc_info=True)

    # ── YouTube Shorts ────────────────────────────────────────

    async def execute_youtube_post(self):
        """Post ELEMNT video as YouTube Short."""
        yt_agent = self.agents.get("youtube")
        if not yt_agent:
            return

        logger.info("Posting YouTube Short...")
        try:
            from strategies.elemnt_content_strategy import ElemntContentStrategy
            elemnt = ElemntContentStrategy(self.weight_manager, self.db)
            content, style, topic = await elemnt.generate_post(platform="youtube")
            post = await yt_agent.post_content(content, style, topic)
            logger.info("YouTube Short: id=%s, style=%s", post.id, style)
        except Exception as e:
            logger.error("YouTube Short failed: %s", e, exc_info=True)

    # ── Reddit ────────────────────────────────────────────────

    async def execute_reddit_comment_cycle(self):
        """Find relevant posts in target subreddits and comment helpfully."""
        reddit_agent = self.agents.get("reddit")
        if not reddit_agent:
            return

        logger.info("Reddit: starting comment cycle...")
        try:
            commented = await reddit_agent.find_and_comment(max_comments=3)
            logger.info("Reddit: commented on %d posts", commented)
        except Exception as e:
            logger.error("Reddit comment cycle failed: %s", e, exc_info=True)

    async def execute_reddit_post(self):
        """Create a post in a target subreddit (respects karma phase + promotion ratio)."""
        reddit_agent = self.agents.get("reddit")
        if not reddit_agent:
            return

        logger.info("Reddit: creating post...")
        try:
            phase = await reddit_agent.get_karma_phase()
            if phase == "comment_only":
                logger.info("Reddit: karma too low for posting (phase=comment_only), skipping")
                return

            from strategies.reddit_content_strategy import RedditContentStrategy
            strategy = RedditContentStrategy(self.weight_manager, self.db)

            karma = await reddit_agent.get_karma()
            result = strategy.select_subreddit_for_post(karma["total_karma"])
            if not result:
                logger.info("Reddit: no eligible subreddit for current karma level")
                return

            subreddit, content_type = result
            title, body = await strategy.generate_post(subreddit, content_type)
            content = f"{title}\n---\n{body}"
            post = await reddit_agent.post_content(content, content_type, "reddit_post")
            logger.info("Reddit post: id=%s, type=%s, sub=r/%s", post.id, content_type, subreddit)
        except Exception as e:
            logger.error("Reddit post failed: %s", e, exc_info=True)

    async def execute_reddit_karma_scrape(self):
        """Scrape current karma levels for tracking."""
        reddit_agent = self.agents.get("reddit")
        if not reddit_agent:
            return

        try:
            metrics = await reddit_agent.scrape_own_metrics()
            if metrics:
                karma = metrics[0]
                phase = await reddit_agent.get_karma_phase()
                logger.info(
                    "Reddit karma: %d (phase=%s)",
                    karma["total_karma"], phase,
                )
        except Exception as e:
            logger.error("Reddit karma scrape failed: %s", e)

    # ── Campaigns ──────────────────────────────────────────────

    async def launch_campaign(self, campaign_id: str):
        """Launch a freebie campaign."""
        own_username = getattr(self.config, "X_USERNAME", "")
        success = await self.campaign_manager.launch_campaign(campaign_id, own_username)
        if success:
            logger.info("Campaign '%s' launched successfully", campaign_id)
        else:
            logger.error("Failed to launch campaign '%s'", campaign_id)

    async def monitor_campaigns(self):
        """Monitor all active campaigns for replies and send DMs."""
        await self.campaign_manager.monitor_all_campaigns()

    async def get_status(self) -> dict:
        platform = self.agent.get_platform_name()
        recent_runs = await self.db.get_recent_runs(limit=10)
        recent_posts = await self.db.get_recent_posts(platform, limit=5)

        weights = {}
        for category in ["content_style", "comment_style", "topic", "post_type"]:
            weights[category] = await self.weight_manager.get_weights_summary(category)

        return {
            "platform": platform,
            "dry_run": self.config.DRY_RUN,
            "recent_runs": [
                {"agent": r.agent, "task": r.task_type, "status": r.status, "started": str(r.started_at)}
                for r in recent_runs
            ],
            "recent_posts": [
                {"id": p.id, "style": p.content_style, "status": p.status, "likes": p.engagement_likes,
                 "content": p.content[:80] + "..." if len(p.content) > 80 else p.content}
                for p in recent_posts
            ],
            "weights": weights,
        }

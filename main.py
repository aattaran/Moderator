"""Moderator CLI — autonomous social media management via Playwright + Gemini."""

import asyncio
import json
import logging
import sys

import click

from config import Settings
from core.orchestrator import Orchestrator
from core.scheduler import TaskScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("moderator")


def get_orchestrator() -> Orchestrator:
    """Create and return an Orchestrator with current settings."""
    config = Settings()
    return Orchestrator(config)


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(debug: bool):
    """Moderator — Autonomous social media management powered by Claude."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.option("--startup-test", is_flag=True, default=False, help="Post one test to each platform on startup")
def run(startup_test: bool):
    """Start the Moderator agent in continuous scheduled mode."""

    async def _run():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()

        scheduler = TaskScheduler(orchestrator.config)
        scheduler.set_callbacks(
            smart_post_callback=orchestrator.execute_smart_post,
            engage_callback=orchestrator.execute_engagement_cycle,
            like_retweet_callback=orchestrator.execute_like_retweet_cycle,
            reply_mentions_callback=orchestrator.execute_reply_to_mentions,
            discovery_callback=orchestrator.execute_discovery_cycle,
            scrape_callback=lambda: orchestrator.execute_metrics_scrape(),
            evaluate_callback=orchestrator.evaluate_weights,
            reflection_callback=orchestrator.execute_content_reflection,
            campaign_monitor_callback=orchestrator.monitor_campaigns,
            facebook_post_callback=orchestrator.execute_facebook_post,
            facebook_engage_callback=orchestrator.execute_facebook_engage,
            facebook_approve_callback=orchestrator.execute_facebook_approve_members,
            instagram_post_callback=orchestrator.execute_instagram_post,
            elemnt_reflection_callback=orchestrator.execute_elemnt_reflection,
            media_sync_callback=orchestrator.execute_media_sync,
            tiktok_post_callback=orchestrator.execute_tiktok_post,
            youtube_post_callback=orchestrator.execute_youtube_post,
            reddit_comment_callback=orchestrator.execute_reddit_comment_cycle,
            reddit_post_callback=orchestrator.execute_reddit_post,
            reddit_karma_callback=orchestrator.execute_reddit_karma_scrape,
        )
        scheduler.setup()
        scheduler.start()

        logger.info("Moderator is running. Press Ctrl+C to stop.")
        logger.info("Upcoming tasks:")
        for job in scheduler.get_next_runs():
            logger.info("  %s → next: %s", job["name"], job["next_run"])

        # Run startup tests only when explicitly requested
        if startup_test and await orchestrator.browser.is_logged_in():
            logger.info("X session active — running startup test...")
            await orchestrator.execute_smart_post()
            logger.info("X startup test complete.")

            # Test ELEMNT platforms if enabled
            if "facebook" in orchestrator.agents:
                logger.info("Testing Facebook post...")
                await orchestrator.execute_facebook_post()
                logger.info("Facebook test complete.")

            if "instagram" in orchestrator.agents:
                logger.info("Testing Instagram post...")
                await orchestrator.execute_instagram_post()
                logger.info("Instagram test complete.")

            if "tiktok" in orchestrator.agents:
                logger.info("Testing TikTok post...")
                await orchestrator.execute_tiktok_post()
                logger.info("TikTok test complete.")

            if "youtube" in orchestrator.agents:
                logger.info("Testing YouTube Short...")
                await orchestrator.execute_youtube_post()
                logger.info("YouTube test complete.")

            if "reddit" in orchestrator.agents:
                logger.info("Testing Reddit comment cycle...")
                await orchestrator.execute_reddit_comment_cycle()
                logger.info("Reddit test complete.")
        else:
            logger.warning("NOT LOGGED IN — posts will fail")

        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
        finally:
            scheduler.stop()
            await orchestrator.shutdown()
            await orchestrator.db.close()

    asyncio.run(_run())


@cli.command()
def post():
    """Execute a single post immediately."""

    async def _post():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_post()

    asyncio.run(_post())


@cli.command()
def engage():
    """Execute a single engagement cycle immediately."""

    async def _engage():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_engagement_cycle()

    asyncio.run(_engage())


@cli.command()
@click.argument("username", required=False, default="")
def scrape(username: str):
    """Scrape engagement metrics from own posts."""

    async def _scrape():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_metrics_scrape(username)

    asyncio.run(_scrape())


@cli.command()
def evaluate():
    """Run weight evaluation using existing engagement data."""

    async def _evaluate():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.evaluate_weights()

    asyncio.run(_evaluate())


@cli.command()
def status():
    """Show current agent status, recent activity, and weights."""

    async def _status():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        info = await orchestrator.get_status()
        print(json.dumps(info, indent=2))

    asyncio.run(_status())


@cli.command(name="analytics")
def show_analytics():
    """Show engagement analytics summary."""

    async def _analytics():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        summary = await orchestrator.analyzer.generate_summary(
            orchestrator.agent.get_platform_name()
        )
        print(summary)

    asyncio.run(_analytics())


@cli.group()
def campaign():
    """Manage freebie campaigns."""
    pass


@campaign.command(name="launch")
@click.argument("campaign_id")
def campaign_launch(campaign_id: str):
    """Launch a freebie campaign (skills, fleet, ppc, video, setup)."""

    async def _launch():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.launch_campaign(campaign_id)

    asyncio.run(_launch())


@campaign.command(name="monitor")
def campaign_monitor():
    """Check replies on active campaigns and send DMs."""

    async def _monitor():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.monitor_campaigns()

    asyncio.run(_monitor())


@campaign.command(name="status")
def campaign_status():
    """Show stats for all campaigns."""

    async def _status():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        stats = await orchestrator.campaign_manager.get_all_stats()
        if not stats:
            print("No active campaigns.")
            return
        for s in stats:
            print(f"  [{s['id']}] {s['name']} — {s['status']}")
            print(f"    Replies: {s['replies']} | Follows: {s['follows']} | DMs: {s['dms_sent']}")
            print(f"    Tweet: {s['tweet_url'] or 'N/A'}")

    asyncio.run(_status())


@cli.command()
def reflect():
    """Run X content reflection — analyze posts and update style guidelines."""

    async def _reflect():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_content_reflection()

    asyncio.run(_reflect())


@cli.command(name="elemnt-reflect")
def elemnt_reflect():
    """Run ELEMNT content reflection for health platforms."""

    async def _reflect():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_elemnt_reflection()

    asyncio.run(_reflect())


@cli.command(name="add-target")
@click.argument("username")
@click.option("--followers", default=0, help="Follower count")
@click.option("--engagement", default=0.05, help="Engagement rate (0-1)")
@click.option("--relevance", default=0.5, help="Relevance score (0-1)")
def add_target(username: str, followers: int, engagement: float, relevance: float):
    """Add a target account for engagement."""

    async def _add():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        target_id = await orchestrator.targeting_strategy.add_target(
            platform=orchestrator.agent.get_platform_name(),
            username=username.lstrip("@"),
            follower_count=followers,
            engagement_rate=engagement,
            relevance_score=relevance,
        )
        print(f"Added target @{username} (id={target_id})")

    asyncio.run(_add())


@cli.command(name="campaign-focus")
@click.argument("campaign_id")
def campaign_focus(campaign_id: str):
    """Switch active campaign focus. Use 'none' to clear."""
    import json
    from pathlib import Path

    path = Path("data/campaigns.json")
    if not path.exists():
        print("No campaigns.json found")
        return

    data = json.loads(path.read_text(encoding="utf-8"))

    if campaign_id == "none":
        data["active_campaign"] = None
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Campaign focus cleared — posting normally")
        return

    if campaign_id not in data.get("campaigns", {}):
        available = list(data.get("campaigns", {}).keys())
        print(f"Campaign '{campaign_id}' not found. Available: {available}")
        return

    data["active_campaign"] = campaign_id
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    campaign = data["campaigns"][campaign_id]
    print(f"Active campaign: {campaign['name']}")
    print(f"Focus: {', '.join(campaign.get('focus_features', [])[:3])}")
    print(f"Threads/day: {campaign.get('daily_threads', 0)}")
    print(f"CTA: {campaign.get('cta', '')}")


@cli.command(name="campaign-list")
def campaign_list_cmd():
    """List all available campaigns."""
    import json
    from pathlib import Path

    path = Path("data/campaigns.json")
    if not path.exists():
        print("No campaigns.json found")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active_campaign")

    for cid, c in data.get("campaigns", {}).items():
        marker = " ← ACTIVE" if cid == active else ""
        dates = ""
        if c.get("start_date"):
            dates = f" ({c['start_date']} → {c.get('end_date', 'ongoing')})"
        print(f"  {cid}: {c['name']}{dates}{marker}")


@cli.command(name="ugc-video")
@click.option("--topic", default="blood_sugar", help="Product topic (blood_sugar, gut_health, longevity, recovery)")
@click.option("--platform", default="instagram", help="Target platform (instagram, tiktok, youtube, facebook, x)")
@click.option("--clips", default=0, help="Clips per video (3-6, 0=use config)")
@click.option("--duration", default=0, help="Seconds per clip (5/8/10, 0=use config)")
@click.option("--actor", default="", help="Path to actor reference photos dir")
@click.option("--scene", default="", help="Path to scene reference image")
@click.option("--gender", default="", help="Actor gender (male/female)")
@click.option("--extend", is_flag=True, help="Extend clips after generation")
@click.option("--style", "style_key", default="", help="Angle style key (random if omitted)")
@click.option("--concept", "concept_key", default="", help="Concept key (random if omitted)")
@click.option("--hook", "hook_key", default="", help="Visual hook key (random if omitted)")
@click.option("--kling-model", default="kling-v3", help="Kling model name")
@click.option("--kling-mode", default="pro", help="Kling mode (std/pro)")
@click.option("--cfg-scale", default=0.7, type=float, help="Kling cfg_scale (0.7 = stricter adherence to start frame)")
@click.option("--sound", default="on", help="Kling sound flag (on/off)")
@click.option("--aspect", "aspect_ratio_override", default="", help="Override platform aspect ratio")
@click.option("--voice", "tts_voice", default="", help="TTS voice override")
@click.option("--pose", default="", help="Director note: actor pose")
@click.option("--bottle-closeup", default="", help="Director note: bottle closeup yes/no")
@click.option("--multi-shot", default="", help="Director note: multi-shot vs continuous")
@click.option("--dry-run", is_flag=True, help="Stop after Stage 2 (preview only)")
@click.option("--scene-description", default="", help="Override scene setting")
def ugc_video(
    topic: str, platform: str, clips: int, duration: int, actor: str, scene: str,
    gender: str, extend: bool, style_key: str, concept_key: str, hook_key: str,
    kling_model: str, kling_mode: str, cfg_scale: float, sound: str,
    aspect_ratio_override: str, tts_voice: str, pose: str, bottle_closeup: str,
    multi_shot: str, dry_run: bool, scene_description: str,
):
    """Generate a UGC video using the proven 6-stage pipeline."""

    async def _gen():
        config = Settings()
        from media.ugc_video_generator import UGCVideoGenerator
        from storage.database import Database

        db = Database(config.DB_PATH)
        await db.initialize()

        vg = UGCVideoGenerator(
            gemini_api_key=config.GEMINI_API_KEY,
            kling_access_key=config.KLING_ACCESS_KEY_ID,
            kling_secret_key=config.KLING_SECRET_KEY,
            fal_api_key=config.FAL_API_KEY,
            db=db,
        )

        # Combine pose/bottle-closeup/multi-shot into a single director_notes string
        notes_parts = []
        if pose:
            notes_parts.append(f"pose: {pose}")
        if bottle_closeup:
            notes_parts.append(f"bottle closeup: {bottle_closeup}")
        if multi_shot:
            notes_parts.append(f"multi-shot: {multi_shot}")
        director_notes = ". ".join(notes_parts) if notes_parts else None

        # Snapshot every CLI arg so UI "Re-run" can reconstruct this invocation.
        import json as _json
        run_params = {
            "source": "cli",
            "topic": topic,
            "platform": platform,
            "clip_count": clips or config.UGC_CLIP_COUNT,
            "clip_duration": duration or config.UGC_CLIP_DURATION,
            "actor_dir": actor or config.UGC_ACTOR_DIR,
            "scene_image": scene or config.UGC_SCENE_IMAGE,
            "scene_description": scene_description or None,
            "actor_gender": gender or config.UGC_ACTOR_GENDER,
            "extend_clips": extend,
            "style_key": style_key or None,
            "concept_key": concept_key or None,
            "visual_hook_key": hook_key or None,
            "kling_model": kling_model,
            "kling_mode": kling_mode,
            "cfg_scale": cfg_scale,
            "sound": sound,
            "aspect_ratio_override": aspect_ratio_override or None,
            "tts_voice": tts_voice or None,
            "pose": pose or None,
            "bottle_closeup": bottle_closeup or None,
            "multi_shot": multi_shot or None,
            "dry_run": dry_run,
        }
        run_params_json = _json.dumps(run_params, separators=(",", ":"))

        result = await vg.generate(
            topic=topic,
            platform=platform,
            clip_count=clips or config.UGC_CLIP_COUNT,
            clip_duration=duration or config.UGC_CLIP_DURATION,
            actor_dir=actor or config.UGC_ACTOR_DIR,
            scene_image=scene or config.UGC_SCENE_IMAGE,
            actor_gender=gender or config.UGC_ACTOR_GENDER,
            extend_clips=extend,
            style_key=style_key or None,
            concept_key=concept_key or None,
            visual_hook_key=hook_key or None,
            kling_model=kling_model,
            kling_mode=kling_mode,
            cfg_scale=cfg_scale,
            sound=sound,
            aspect_ratio_override=aspect_ratio_override or None,
            tts_voice=tts_voice or None,
            director_notes=director_notes,
            scene_description=scene_description or None,
            dry_run=dry_run,
            run_params_json=run_params_json,
        )
        print(f"Video generated: {result}")

    asyncio.run(_gen())


@cli.command(name="reddit-post")
def reddit_post():
    """Post to a Reddit subreddit."""

    async def _post():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_reddit_post()

    asyncio.run(_post())


@cli.command(name="reddit-engage")
def reddit_engage():
    """Run Reddit comment cycle — find posts and comment helpfully."""

    async def _engage():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_reddit_comment_cycle()

    asyncio.run(_engage())


@cli.command(name="reddit-karma")
def reddit_karma():
    """Show current Reddit karma."""

    async def _karma():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        await orchestrator.execute_reddit_karma_scrape()

    asyncio.run(_karma())


@cli.command(name="ui")
def run_ui():
    """Launch the UGC web UI on 127.0.0.1:8765."""
    import uvicorn
    uvicorn.run("ui.server:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    cli()

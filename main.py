"""Moderator CLI — autonomous social media management via Claude Computer Use."""

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
def run():
    """Start the Moderator agent in continuous scheduled mode."""

    async def _run():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()

        scheduler = TaskScheduler(orchestrator.config)
        scheduler.set_callbacks(
            post_callback=orchestrator.execute_post,
            engage_callback=orchestrator.execute_engagement_cycle,
            scrape_callback=lambda: orchestrator.execute_metrics_scrape(),
            evaluate_callback=orchestrator.evaluate_weights,
        )
        scheduler.setup()
        scheduler.start()

        logger.info("Moderator is running. Press Ctrl+C to stop.")
        logger.info("Upcoming tasks:")
        for job in scheduler.get_next_runs():
            logger.info("  %s → next: %s", job["name"], job["next_run"])

        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
            scheduler.stop()

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


if __name__ == "__main__":
    cli()

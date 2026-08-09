"""Freebie campaign engine — post campaigns, monitor replies, auto-DM download links."""

import asyncio
import logging
import random
from datetime import datetime

from config import Settings
from core.x_actions import XActions
from storage.database import Database
from storage.models import Campaign, CampaignFulfillment

logger = logging.getLogger(__name__)

# Pre-configured campaigns
CAMPAIGN_CONFIGS = {
    "skills": Campaign(
        campaign_id="skills",
        freebie_name="7 Claude Code Skills Pack",
        keyword="SKILLS",
        download_url="https://github.com/aattaran/freebies/tree/main/claude-code-skills",
        tweet_text=(
            "I use 7 custom Claude Code skills daily.\n\n"
            "They handle:\n"
            "- Systematic debugging (trace, don't guess)\n"
            "- 4-pass code review\n"
            "- Security audits\n"
            "- Multi-agent orchestration\n"
            "- Token optimization\n\n"
            "Took months to refine. Yours free.\n\n"
            "Reply 'SKILLS' + follow to get them."
        ),
        dm_template=(
            "Here's your Claude Code Skills Pack! 🎁\n\n"
            "{url}\n\n"
            "7 skills: debug, review, audit, bulletproof, code, orchestrate, tokenopt.\n"
            "Drop them in ~/.claude/skills/ and they work instantly.\n\n"
            "If they save you time, a retweet would help others find them too 🙏"
        ),
    ),
    "fleet": Campaign(
        campaign_id="fleet",
        freebie_name="Fleet Commander Plugin",
        keyword="FLEET",
        download_url="https://github.com/aattaran/fleet-commander",
        tweet_text=(
            "Built a Claude Code plugin that deploys coordinated AI agent teams.\n\n"
            "Pick roles (planner, coder, debugger, reviewer), models, effort levels "
            "— then launch a parallel fleet.\n\n"
            "One command: /plugin install fleet-commander\n\n"
            "Reply 'FLEET' + follow to get the install link."
        ),
        dm_template=(
            "Here's Fleet Commander! 🚀\n\n"
            "{url}\n\n"
            "Install: /plugin install fleet-commander\n"
            "Then ask Claude to 'deploy a fleet' — it walks you through setup.\n\n"
            "If you find it useful, a retweet helps others discover it 🙏"
        ),
    ),
    "ppc": Campaign(
        campaign_id="ppc",
        freebie_name="Amazon PPC Automation Rules",
        keyword="PPC",
        download_url="https://github.com/aattaran/freebies/tree/main/amazon-ppc-rules",
        tweet_text=(
            "I reverse-engineered 3 Amazon PPC automation strategies from top sellers:\n\n"
            "🦊 Smart Fox — conservative, profit-first\n"
            "🐨 Calm Koala — balanced growth\n"
            "🐊 Crocodile Growth — aggressive scaling\n\n"
            "Complete rule sets with bid logic and ACOS targets.\n\n"
            "Reply 'PPC' + follow to get them."
        ),
        dm_template=(
            "Here are your Amazon PPC automation rules! 📊\n\n"
            "{url}\n\n"
            "3 strategies: Smart Fox, Calm Koala, Crocodile Growth.\n"
            "Each has complete bid rules, ACOS targets, and campaign structure.\n\n"
            "If they help your campaigns, a retweet means a lot 🙏"
        ),
    ),
    "video": Campaign(
        campaign_id="video",
        freebie_name="AI Video Ad Pipeline Templates",
        keyword="VIDEO",
        download_url="https://github.com/aattaran/freebies/tree/main/video-ad-templates",
        tweet_text=(
            "I built a pipeline that turns a product listing into a cinematic video ad.\n\n"
            "10 stages, fully AI-automated:\n"
            "Product data → Script → Scenes → Voiceover → Music → Final cut\n\n"
            "Uses Kling + KIE for generation.\n\n"
            "Reply 'VIDEO' + follow to get the templates."
        ),
        dm_template=(
            "Here are your AI Video Ad templates! 🎬\n\n"
            "{url}\n\n"
            "Includes product JSON format, director guidelines, and scene templates.\n"
            "Plug in your product data and let AI generate the ad.\n\n"
            "If you make something cool with it, tag me! 🙏"
        ),
    ),
    "setup": Campaign(
        campaign_id="setup",
        freebie_name="Solo Founder AI Setup",
        keyword="SETUP",
        download_url="https://github.com/aattaran/freebies/tree/main/solo-founder-setup",
        tweet_text=(
            "My complete AI dev setup as a solo founder:\n\n"
            "- CLAUDE.md (project rules)\n"
            "- 7 custom skills\n"
            "- MCP server configs\n"
            "- Git hooks\n"
            "- Security rules\n\n"
            "One config makes Claude Code 10x more productive.\n\n"
            "Reply 'SETUP' + follow to get the full config."
        ),
        dm_template=(
            "Here's my complete AI dev setup! ⚡\n\n"
            "{url}\n\n"
            "CLAUDE.md, 7 skills, MCP configs, hooks — everything I use daily.\n"
            "Drop the files in ~/.claude/ and you're set.\n\n"
            "If it levels up your workflow, a retweet helps others find it 🙏"
        ),
    ),
}


class FreebieCampaignManager:
    """Manages freebie giveaway campaigns on X."""

    def __init__(self, db: Database, actions: XActions, config: Settings):
        self.db = db
        self.actions = actions
        self.config = config

    async def launch_campaign(self, campaign_id: str, own_username: str = "") -> bool:
        """Post a campaign tweet and start tracking."""
        campaign_config = CAMPAIGN_CONFIGS.get(campaign_id)
        if not campaign_config:
            logger.error("Unknown campaign: %s. Available: %s", campaign_id, list(CAMPAIGN_CONFIGS.keys()))
            return False

        # Check if already active
        existing = await self.db.get_campaign(campaign_id)
        if existing and existing.status == "active":
            logger.warning("Campaign '%s' is already active (tweet: %s)", campaign_id, existing.tweet_url)
            return False

        # Post the tweet
        success = await self.actions.compose_and_post(campaign_config.tweet_text)
        if not success:
            logger.error("Failed to post campaign tweet for '%s'", campaign_id)
            return False

        # Get the tweet URL — use config username as fallback
        if not own_username:
            own_username = getattr(self.config, "X_USERNAME", "")
        tweet_url = None
        if own_username:
            tweet_url = await self.actions.get_own_latest_tweet_url(own_username)
        if not tweet_url:
            logger.warning("Could not capture tweet URL for campaign '%s' — set X_USERNAME in .env", campaign_id)

        # Save to DB (create a copy so we don't mutate the config template)
        campaign = Campaign(
            campaign_id=campaign_config.campaign_id,
            tweet_text=campaign_config.tweet_text,
            keyword=campaign_config.keyword,
            download_url=campaign_config.download_url,
            freebie_name=campaign_config.freebie_name,
            dm_template=campaign_config.dm_template,
            tweet_url=tweet_url,
            status="active",
        )
        await self.db.insert_campaign(campaign)

        logger.info(
            "Campaign '%s' launched — tweet: %s",
            campaign_id, tweet_url or "URL not captured",
        )
        return True

    async def monitor_all_campaigns(self):
        """Check replies on all active campaigns and fulfill pending DMs."""
        campaigns = await self.db.get_active_campaigns()
        if not campaigns:
            logger.debug("No active campaigns to monitor")
            return

        max_dms = self.config.MAX_DMS_PER_HOUR

        # Check how many DMs we already sent in the last hour (across all campaigns)
        recent_dms = await self.db.count_dms_sent_recently(hours=1)
        remaining_budget = max(0, max_dms - recent_dms)
        if remaining_budget == 0:
            logger.info("DM hourly limit already reached (%d sent) — skipping", recent_dms)
            return

        total_dms_this_run = 0

        for campaign in campaigns:
            if not campaign.tweet_url:
                logger.warning("Campaign '%s' has no tweet URL — skipping", campaign.campaign_id)
                continue

            dms_for_campaign = 0

            try:
                # Scrape replies for keyword
                new_users = await self.actions.get_tweet_replies(
                    campaign.tweet_url, campaign.keyword
                )
            except Exception as e:
                logger.error("Failed to scrape replies for campaign '%s': %s", campaign.campaign_id, e)
                continue

            # Record new fulfillments (INSERT OR IGNORE prevents duplicates)
            for username in new_users:
                await self.db.insert_fulfillment(CampaignFulfillment(
                    campaign_id=campaign.campaign_id,
                    username=username,
                    replied_at=datetime.now(),
                ))

            # Process unfulfilled users — cap follow-checks per run to avoid X ban
            MAX_FOLLOW_CHECKS_PER_RUN = 20
            unfulfilled = await self.db.get_unfulfilled(campaign.campaign_id)
            follow_checks_this_run = 0
            for f in unfulfilled:
                if follow_checks_this_run >= MAX_FOLLOW_CHECKS_PER_RUN:
                    logger.info("Follow check cap reached (%d) — deferring remaining to next run", MAX_FOLLOW_CHECKS_PER_RUN)
                    break
                if total_dms_this_run >= remaining_budget:
                    logger.info("DM budget exhausted (%d/%d) — stopping", total_dms_this_run + recent_dms, max_dms)
                    break

                # Check if they follow us
                follow_checks_this_run += 1
                try:
                    follow_status = await self.actions.check_if_following(f.username)
                except Exception as e:
                    logger.warning("Error checking follow for @%s: %s — skipping", f.username, e)
                    continue

                # None means account is suspended/private/unavailable
                if follow_status is None:
                    await self.db.mark_skipped(campaign.campaign_id, f.username, "unavailable")
                    logger.info("@%s unavailable — marked as skipped", f.username)
                    continue

                if not follow_status:
                    logger.info("@%s replied but doesn't follow — skipping DM", f.username)
                    continue

                # Build DM text — prefer template from DB, fall back to config
                dm_template = campaign.dm_template
                if not dm_template:
                    config_tmpl = CAMPAIGN_CONFIGS.get(campaign.campaign_id)
                    dm_template = config_tmpl.dm_template if config_tmpl else ""
                if not dm_template:
                    logger.error("No DM template for campaign '%s' — skipping", campaign.campaign_id)
                    continue

                dm_text = dm_template.replace("{url}", campaign.download_url)

                # Send DM with error handling (don't crash the whole run)
                try:
                    success = await self.actions.send_dm(f.username, dm_text)
                except Exception as e:
                    logger.error("Exception sending DM to @%s: %s", f.username, e)
                    await self.db.mark_skipped(campaign.campaign_id, f.username, "dm_failed")
                    continue

                if success:
                    await self.db.mark_fulfilled(campaign.campaign_id, f.username)
                    dms_for_campaign += 1
                    total_dms_this_run += 1
                    logger.info("DM sent to @%s for campaign '%s' (%d/%d budget)",
                                f.username, campaign.campaign_id, total_dms_this_run + recent_dms, max_dms)
                else:
                    logger.warning("Failed to DM @%s — marking as failed", f.username)
                    await self.db.mark_skipped(campaign.campaign_id, f.username, "dm_failed")
                    # Don't break the whole loop — continue with next user
                    continue

                # Random delay between DMs (30-90s) to avoid rate limits
                await asyncio.sleep(random.uniform(30, 90))

            # Update stats from actual DB counts (source of truth)
            counts = await self.db.get_fulfillment_count(campaign.campaign_id)
            await self.db.update_campaign_stats(
                campaign.campaign_id,
                replies=counts["total"],
                follows=0,  # We don't track follows separately yet
                dms=counts["dms_sent"],
            )

        logger.info("Campaign monitor complete — %d DMs sent this run", total_dms_this_run)

    async def get_all_stats(self) -> list[dict]:
        """Get stats for all campaigns (active and completed)."""
        # Get active campaigns
        active = await self.db.get_active_campaigns()
        result = []
        for c in active:
            counts = await self.db.get_fulfillment_count(c.campaign_id)
            result.append({
                "id": c.campaign_id,
                "name": c.freebie_name,
                "status": c.status,
                "replies": counts["total"],
                "dms_sent": counts["dms_sent"],
                "skipped": counts["skipped"],
                "tweet_url": c.tweet_url,
            })
        return result

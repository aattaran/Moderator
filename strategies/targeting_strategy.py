"""Dynamic targeting strategy — discovers, scores, and prunes accounts automatically."""

import logging
import random
from datetime import datetime, timedelta

from storage.database import Database
from storage.models import TargetAccount

logger = logging.getLogger(__name__)

# Minimum engagement ROI to keep a target active
MIN_ROI_THRESHOLD = 0.0
# Maximum active targets to maintain
MAX_ACTIVE_TARGETS = 50
# Minimum targets before forcing discovery
MIN_ACTIVE_TARGETS = 10

# ── Political filter — never engage with political accounts/content ───
POLITICAL_KEYWORDS = {
    # Politicians, parties, government
    "democrat", "republican", "gop", "maga", "liberal", "conservative",
    "trump", "biden", "obama", "desantis", "rfk", "vivek", "newsom",
    "congress", "senate", "politician", "politics",
    "political", "election", "vote", "voting", "ballot",
    "left-wing", "right-wing", "leftist", "rightwing", "progressive",
    "bipartisan", "partisan", "caucus", "primary", "midterm",
    # Elected office titles (catches state/local officials like Derric Evans)
    "delegate", "assemblyman", "assemblywoman", "councilman", "councilwoman",
    "alderman", "mayor", "commissioner", "state rep", "state senator",
    "city council", "school board", "elected official",
    # Hot-button political topics
    "abortion", "pro-life", "pro-choice", "gun control", "2nd amendment",
    "second amendment", "gun rights", "gun reform",
    "immigration", "border wall", "deportation", "refugee", "illegal alien",
    "open borders", "border crisis", "amnesty",
    "socialism", "communism", "fascism", "marxism", "antifa",
    "blm", "defund", "woke", "anti-woke", "cancel culture",
    "critical race", "crt", "dei", "affirmative action",
    "lgbtq", "trans rights", "drag queen", "gender ideology",
    "climate hoax", "green new deal",
    # Government/policy
    "legislation", "executive order", "supreme court", "scotus",
    "governor", "senator", "congressman", "congresswoman", "representative",
    "white house", "capitol", "pentagon",
    "filibuster", "impeach", "indictment", "pardon",
    "tax reform", "government shutdown", "national debt",
    # International politics
    "geopolitics", "sanctions", "nato", "warfare", "military",
    "israel", "palestine", "gaza", "ukraine", "russia",
    "china threat", "taiwan strait", "north korea",
    # Partisan media / political commentators
    "fox news", "msnbc", "cnn politics", "breitbart", "infowars",
    "daily wire", "newsmax", "oann", "the blaze",
    "tucker carlson", "ben shapiro", "matt walsh", "candace owens",
    "rachel maddow", "sean hannity", "alex jones",
    # Campaign / fundraising
    "donate to", "fundraiser for", "pac", "super pac", "grassroots",
    "rally", "town hall", "constituent",
}


def is_political(text: str) -> bool:
    """Check if text contains political content using word-boundary matching."""
    import re
    lower = text.lower()
    return any(
        re.search(r'\b' + re.escape(kw) + r'\b', lower)
        for kw in POLITICAL_KEYWORDS
    )


class TargetingStrategy:
    """Dynamic targeting — discovers new accounts, evaluates ROI, prunes losers."""

    def __init__(self, db: Database):
        self.db = db

    async def select_target(self, platform: str) -> TargetAccount | None:
        """Select a target using weighted random. Prefers high-ROI accounts."""
        accounts = await self.db.get_active_targets(platform, limit=50)
        if not accounts:
            logger.warning("No active targets for %s", platform)
            return None

        scored = []
        for account in accounts:
            # Score = relevance * engagement_rate, with a floor
            score = max(account.relevance_score * max(account.avg_engagement_rate, 0.01), 0.01)
            scored.append((account, score))

        accounts_list = [a for a, _ in scored]
        weights = [s for _, s in scored]
        selected = random.choices(accounts_list, weights=weights, k=1)[0]

        logger.info("Selected: @%s (relevance=%.2f, engagement=%.3f)",
                     selected.username, selected.relevance_score, selected.avg_engagement_rate)
        return selected

    async def add_target(self, platform: str, username: str,
                         follower_count: int = 0, engagement_rate: float = 0.01,
                         relevance_score: float = 0.5) -> int:
        """Add or update a target account."""
        account = TargetAccount(
            platform=platform, username=username,
            follower_count=follower_count,
            avg_engagement_rate=engagement_rate,
            relevance_score=relevance_score,
            last_checked=datetime.now(),
        )
        return await self.db.upsert_target_account(account)

    async def get_all_targets(self, platform: str) -> list[TargetAccount]:
        return await self.db.get_active_targets(platform, limit=100)

    async def ingest_discovered_accounts(self, platform: str, discovered: list[dict]):
        """Add newly discovered accounts as targets with initial scores."""
        existing = await self.db.get_active_targets(platform, limit=200)
        existing_usernames = {a.username.lower() for a in existing}

        added = 0
        skipped_political = 0
        for account in discovered:
            username = account.get("username", "").strip()
            if not username or username.lower() in existing_usernames:
                continue

            # Skip political accounts
            bio = account.get("bio", "") or account.get("description", "") or ""
            if is_political(username) or is_political(bio):
                skipped_political += 1
                continue

            # Start with moderate relevance — will be adjusted by ROI evaluation
            followers = account.get("followers", 0)
            engagement_signal = account.get("engagement_signal", 0)

            # Initial relevance based on engagement signal
            initial_relevance = min(0.3 + (engagement_signal / 1000) * 0.1, 0.7)

            await self.add_target(
                platform=platform,
                username=username,
                follower_count=followers,
                engagement_rate=0.02,  # Conservative starting estimate
                relevance_score=initial_relevance,
            )
            existing_usernames.add(username.lower())
            added += 1

            if len(existing_usernames) >= MAX_ACTIVE_TARGETS:
                break

        if added:
            logger.info("Ingested %d new target accounts", added)
        if skipped_political:
            logger.info("Skipped %d political accounts", skipped_political)

    async def evaluate_targets(self, platform: str):
        """Evaluate all targets based on engagement ROI and adjust scores.

        ROI = engagement we received on comments to this account /
              number of times we engaged with them.

        High ROI → boost relevance_score
        Low ROI → lower relevance_score
        Zero engagement after 5+ attempts → deactivate
        """
        targets = await self.db.get_active_targets(platform, limit=100)
        week_ago = datetime.now() - timedelta(days=7)

        for target in targets:
            # Count our comments to this target in the last 7 days
            comments = await self.db.get_comments_by_target(platform, target.username, week_ago)
            if len(comments) < 2:
                continue  # Not enough data

            # Calculate engagement we got back
            total_likes = sum(c.engagement_likes for c in comments)
            total_replies = sum(c.engagement_replies for c in comments)
            total_engagement = total_likes + total_replies
            avg_roi = total_engagement / len(comments) if comments else 0

            # Adjust relevance score
            old_relevance = target.relevance_score
            if avg_roi > 2:
                # Great ROI — boost
                target.relevance_score = min(1.0, target.relevance_score + 0.1)
            elif avg_roi > 0.5:
                # Decent ROI — small boost
                target.relevance_score = min(1.0, target.relevance_score + 0.03)
            elif avg_roi < 0.1 and len(comments) >= 5:
                # Poor ROI after many attempts — lower score
                target.relevance_score = max(0.05, target.relevance_score - 0.1)
            elif avg_roi == 0 and len(comments) >= 8:
                # Zero engagement after 8+ attempts — deactivate
                target.active = False
                logger.info("Deactivating @%s — zero ROI after %d comments", target.username, len(comments))

            target.avg_engagement_rate = avg_roi / 10  # Normalize to 0-1 range
            target.last_checked = datetime.now()

            await self.db.upsert_target_account(target)

            if old_relevance != target.relevance_score:
                logger.info("@%s relevance: %.2f → %.2f (avg_roi=%.1f, comments=%d)",
                            target.username, old_relevance, target.relevance_score,
                            avg_roi, len(comments))

    async def needs_discovery(self, platform: str) -> bool:
        """Check if we need to discover more accounts."""
        targets = await self.db.get_active_targets(platform, limit=100)
        return len(targets) < MIN_ACTIVE_TARGETS

"""Async SQLite database wrapper with WAL mode."""

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from storage.models import (
    AgentRun, Campaign, CampaignFulfillment, Comment, FlashSale,
    Post, StyleGuideline, TargetAccount, WeightEntry,
)

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    def __init__(self, db_path: str = "data/moderator.db"):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self):
        """Run migrations and set pragmas."""
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        db = await self._get_conn()
        if self.db_path != ":memory:":
            await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        migration_file = MIGRATIONS_DIR / "001_initial.sql"
        sql = migration_file.read_text()
        await db.executescript(sql)
        await db.commit()

        # Run incremental migrations
        for mig in sorted(MIGRATIONS_DIR.glob("0*.sql")):
            if mig.name == "001_initial.sql":
                continue
            try:
                await db.executescript(mig.read_text())
                await db.commit()
            except Exception as e:
                logger.warning("Migration %s skipped (may already exist): %s", mig.name, e)
        logger.info("Database initialized at %s", self.db_path)

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    # --- Posts ---

    async def insert_post(self, post: Post) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO posts (platform, content, content_style, topic, media_urls,
               posted_at, status, engagement_likes, engagement_reposts,
               engagement_replies, engagement_views)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post.platform, post.content, post.content_style, post.topic,
                json.dumps(post.media_urls), post.posted_at, post.status,
                post.engagement_likes, post.engagement_reposts,
                post.engagement_replies, post.engagement_views,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def update_post_status(self, post_id: int, status: str, posted_at: datetime | None = None):
        db = await self._get_conn()
        if posted_at:
            await db.execute(
                "UPDATE posts SET status=?, posted_at=? WHERE id=?",
                (status, posted_at, post_id),
            )
        else:
            await db.execute("UPDATE posts SET status=? WHERE id=?", (status, post_id))
        await db.commit()

    async def update_post_engagement(
        self, post_id: int, likes: int, reposts: int, replies: int, views: int
    ):
        db = await self._get_conn()
        await db.execute(
            """UPDATE posts SET engagement_likes=?, engagement_reposts=?,
               engagement_replies=?, engagement_views=?, scraped_at=?
               WHERE id=?""",
            (likes, reposts, replies, views, datetime.now(), post_id),
        )
        await db.commit()

    async def get_recent_posts(self, platform: str, limit: int = 50) -> list[Post]:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM posts WHERE platform=? ORDER BY created_at DESC LIMIT ?",
            (platform, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_post(row) for row in rows]

    async def count_posts_today(self, platform: str) -> int:
        db = await self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await db.execute(
            """SELECT COUNT(*) FROM posts
               WHERE platform=? AND status='posted'
               AND posted_at LIKE ?""",
            (platform, f"{today}%"),
        )
        row = await cursor.fetchone()
        return row[0]

    async def get_posts_by_style(
        self, platform: str, style: str, since: datetime, until: datetime
    ) -> list[Post]:
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM posts WHERE platform=? AND content_style=?
               AND status='posted' AND posted_at BETWEEN ? AND ?""",
            (platform, style, since, until),
        )
        rows = await cursor.fetchall()
        return [self._row_to_post(row) for row in rows]

    def _row_to_post(self, row) -> Post:
        return Post(
            id=row["id"], platform=row["platform"], content=row["content"],
            content_style=row["content_style"],
            topic=row["topic"] if "topic" in row.keys() else None,
            media_urls=json.loads(row["media_urls"]) if row["media_urls"] else [],
            posted_at=row["posted_at"], status=row["status"],
            engagement_likes=row["engagement_likes"],
            engagement_reposts=row["engagement_reposts"],
            engagement_replies=row["engagement_replies"],
            engagement_views=row["engagement_views"],
            scraped_at=row["scraped_at"], created_at=row["created_at"],
        )

    async def get_media_last_posted(self, platform: str) -> dict[str, str]:
        """Map each published media filename to when it last went out.

        Backs post-once rotation: a filename absent from this map has never been
        posted on that platform. Reads the existing posts.media_urls ledger rather
        than keeping a second source of truth.
        """
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT media_urls, posted_at FROM posts
               WHERE platform=? AND status='posted' AND media_urls IS NOT NULL
               ORDER BY posted_at""",
            (platform,),
        )
        rows = await cursor.fetchall()

        last_posted: dict[str, str] = {}
        for row in rows:
            try:
                names = json.loads(row["media_urls"] or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            # Rows are ordered oldest-first, so later writes leave the most recent time.
            for name in names:
                last_posted[name] = row["posted_at"] or ""
        return last_posted

    # --- Comments ---

    async def insert_comment(self, comment: Comment) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO comments (platform, target_post_url, target_author,
               content, comment_style, topic, posted_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                comment.platform, comment.target_post_url, comment.target_author,
                comment.content, comment.comment_style, comment.topic,
                comment.posted_at, comment.status,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def count_comments_last_hour(self, platform: str) -> int:
        db = await self._get_conn()
        from datetime import timedelta
        one_hour_ago = str(datetime.now() - timedelta(hours=1))
        cursor = await db.execute(
            """SELECT COUNT(*) FROM comments
               WHERE platform=? AND status='posted'
               AND posted_at >= ?""",
            (platform, one_hour_ago),
        )
        row = await cursor.fetchone()
        return row[0]

    async def get_comments_by_style(
        self, platform: str, style: str, since: datetime, until: datetime
    ) -> list[Comment]:
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM comments WHERE platform=? AND comment_style=?
               AND status='posted' AND posted_at BETWEEN ? AND ?""",
            (platform, style, since, until),
        )
        rows = await cursor.fetchall()
        return [self._row_to_comment(row) for row in rows]

    async def get_comments_by_topic(
        self, platform: str, topic: str, since: datetime, until: datetime
    ) -> list[Comment]:
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM comments WHERE platform=? AND topic=?
               AND status='posted' AND posted_at BETWEEN ? AND ?""",
            (platform, topic, since, until),
        )
        rows = await cursor.fetchall()
        return [self._row_to_comment(row) for row in rows]

    async def get_comments_by_target(
        self, platform: str, target_username: str, since: datetime
    ) -> list[Comment]:
        """Get all comments we posted to a specific target since a given date."""
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM comments WHERE platform=? AND target_author=?
               AND status='posted' AND posted_at >= ?
               ORDER BY posted_at DESC""",
            (platform, target_username, since),
        )
        rows = await cursor.fetchall()
        return [self._row_to_comment(row) for row in rows]

    async def deactivate_target(self, platform: str, username: str):
        """Set a target account to inactive."""
        db = await self._get_conn()
        await db.execute(
            "UPDATE target_accounts SET active=0 WHERE platform=? AND username=?",
            (platform, username),
        )
        await db.commit()

    def _row_to_comment(self, row) -> Comment:
        return Comment(
            id=row["id"], platform=row["platform"],
            target_post_url=row["target_post_url"], target_author=row["target_author"],
            content=row["content"], comment_style=row["comment_style"],
            topic=row["topic"], posted_at=row["posted_at"], status=row["status"],
            engagement_likes=row["engagement_likes"],
            engagement_replies=row["engagement_replies"],
            scraped_at=row["scraped_at"], created_at=row["created_at"],
        )

    # --- Target Accounts ---

    async def upsert_target_account(self, account: TargetAccount) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO target_accounts (platform, username, follower_count,
               avg_engagement_rate, relevance_score, last_checked, active)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, username) DO UPDATE SET
               follower_count=excluded.follower_count,
               avg_engagement_rate=excluded.avg_engagement_rate,
               relevance_score=excluded.relevance_score,
               last_checked=excluded.last_checked""",
            (
                account.platform, account.username, account.follower_count,
                account.avg_engagement_rate, account.relevance_score,
                account.last_checked, account.active,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_active_targets(self, platform: str, limit: int = 20) -> list[TargetAccount]:
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM target_accounts
               WHERE platform=? AND active=1
               ORDER BY relevance_score DESC LIMIT ?""",
            (platform, limit),
        )
        rows = await cursor.fetchall()
        return [
            TargetAccount(
                id=row["id"], platform=row["platform"], username=row["username"],
                follower_count=row["follower_count"],
                avg_engagement_rate=row["avg_engagement_rate"],
                relevance_score=row["relevance_score"],
                last_checked=row["last_checked"], active=bool(row["active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # --- Weight Entries ---

    async def get_current_weights(self, category: str) -> list[WeightEntry]:
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM weight_entries
               WHERE category=? AND period_end IS NULL
               ORDER BY name""",
            (category,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_weight(row) for row in rows]

    async def upsert_weight_entry(self, entry: WeightEntry):
        db = await self._get_conn()
        await db.execute(
            """INSERT INTO weight_entries (category, name, weight, period_start,
               period_end, sample_count, avg_engagement)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(category, name, period_start) DO UPDATE SET
               weight=excluded.weight, period_end=excluded.period_end,
               sample_count=excluded.sample_count,
               avg_engagement=excluded.avg_engagement""",
            (
                entry.category, entry.name, entry.weight, entry.period_start,
                entry.period_end, entry.sample_count, entry.avg_engagement,
            ),
        )
        await db.commit()

    async def initialize_weights(self, category: str, names: list[str], period_start: datetime):
        """Seed initial weights for a category if none exist."""
        existing = await self.get_current_weights(category)
        if existing:
            return
        for name in names:
            entry = WeightEntry(
                category=category, name=name, weight=1.0, period_start=period_start,
            )
            await self.upsert_weight_entry(entry)

    def _row_to_weight(self, row) -> WeightEntry:
        return WeightEntry(
            id=row["id"], category=row["category"], name=row["name"],
            weight=row["weight"], period_start=row["period_start"],
            period_end=row["period_end"], sample_count=row["sample_count"],
            avg_engagement=row["avg_engagement"], created_at=row["created_at"],
        )

    # --- Agent Runs ---

    async def log_agent_run(self, run: AgentRun) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO agent_runs (agent, task_type, started_at, status)
               VALUES (?, ?, ?, ?)""",
            (run.agent, run.task_type, run.started_at or datetime.now(), run.status),
        )
        await db.commit()
        return cursor.lastrowid

    async def complete_agent_run(
        self, run_id: int, status: str, iterations: int = 0,
        error_message: str | None = None, api_tokens_used: int = 0
    ):
        db = await self._get_conn()
        await db.execute(
            """UPDATE agent_runs SET completed_at=?, status=?, iterations=?,
               error_message=?, api_tokens_used=? WHERE id=?""",
            (datetime.now(), status, iterations, error_message, api_tokens_used, run_id),
        )
        await db.commit()

    # --- Style Guidelines ---

    async def get_active_guideline(self, platform: str = "x") -> StyleGuideline | None:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM style_guidelines WHERE active=1 AND platform=? ORDER BY version DESC LIMIT 1",
            (platform,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return StyleGuideline(
            id=row["id"], version=row["version"],
            guidelines_text=row["guidelines_text"],
            analysis_summary=row["analysis_summary"],
            platform=row["platform"] if "platform" in row.keys() else "x",
            top_patterns=json.loads(row["top_patterns"]),
            anti_patterns=json.loads(row["anti_patterns"]),
            posts_analyzed=row["posts_analyzed"],
            avg_engagement_score=row["avg_engagement_score"],
            active=bool(row["active"]), created_at=row["created_at"],
        )

    async def insert_style_guideline(self, guideline: StyleGuideline) -> int:
        db = await self._get_conn()
        # Deactivate existing guidelines for this platform only
        await db.execute(
            "UPDATE style_guidelines SET active=0 WHERE platform=?",
            (guideline.platform,),
        )
        cursor = await db.execute(
            """INSERT INTO style_guidelines (version, guidelines_text, analysis_summary,
               top_patterns, anti_patterns, posts_analyzed, avg_engagement_score, active, platform)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                guideline.version, guideline.guidelines_text,
                guideline.analysis_summary,
                json.dumps(guideline.top_patterns),
                json.dumps(guideline.anti_patterns),
                guideline.posts_analyzed, guideline.avg_engagement_score,
                guideline.platform,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_posts_with_engagement(
        self, platform: str, min_age_hours: int = 48, limit: int = 100
    ) -> list[Post]:
        """Get posted tweets that have had time to accumulate engagement."""
        db = await self._get_conn()
        from datetime import timedelta
        cutoff = str(datetime.now() - timedelta(hours=min_age_hours))
        cursor = await db.execute(
            """SELECT * FROM posts
               WHERE platform=? AND status='posted' AND posted_at <= ?
               ORDER BY posted_at DESC LIMIT ?""",
            (platform, cutoff, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_post(row) for row in rows]

    async def get_next_guideline_version(self, platform: str = "x") -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM style_guidelines WHERE platform=?",
            (platform,),
        )
        row = await cursor.fetchone()
        return row[0]

    # --- Campaigns ---

    async def insert_campaign(self, campaign: Campaign) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO campaigns (campaign_id, tweet_text, keyword, download_url,
               freebie_name, dm_template, tweet_url, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                campaign.campaign_id, campaign.tweet_text, campaign.keyword,
                campaign.download_url, campaign.freebie_name, campaign.dm_template,
                campaign.tweet_url, campaign.status,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_campaign(self, campaign_id: str) -> Campaign | None:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_campaign(row)

    async def get_active_campaigns(self) -> list[Campaign]:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM campaigns WHERE status='active' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_campaign(row) for row in rows]

    async def update_campaign_status(self, campaign_id: str, status: str, tweet_url: str | None = None):
        db = await self._get_conn()
        if tweet_url:
            await db.execute(
                "UPDATE campaigns SET status=?, tweet_url=? WHERE campaign_id=?",
                (status, tweet_url, campaign_id),
            )
        else:
            await db.execute(
                "UPDATE campaigns SET status=? WHERE campaign_id=?", (status, campaign_id)
            )
        await db.commit()

    async def update_campaign_stats(self, campaign_id: str, replies: int, follows: int, dms: int):
        db = await self._get_conn()
        await db.execute(
            """UPDATE campaigns SET replies_count=?, follows_count=?, dms_sent=?
               WHERE campaign_id=?""",
            (replies, follows, dms, campaign_id),
        )
        await db.commit()

    async def insert_fulfillment(self, f: CampaignFulfillment) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT OR IGNORE INTO campaign_fulfillments
               (campaign_id, username, replied_at, is_following, dm_sent)
               VALUES (?, ?, ?, ?, ?)""",
            (f.campaign_id, f.username, f.replied_at, f.is_following, f.dm_sent),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_unfulfilled(self, campaign_id: str) -> list[CampaignFulfillment]:
        """Get users who replied but haven't been DM'd and aren't skipped."""
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM campaign_fulfillments
               WHERE campaign_id=? AND dm_sent=0 AND skip_reason IS NULL
               ORDER BY created_at ASC""",
            (campaign_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_fulfillment(row) for row in rows]

    async def count_dms_sent_recently(self, hours: int = 1) -> int:
        """Count DMs sent across all campaigns in the last N hours."""
        db = await self._get_conn()
        from datetime import timedelta
        cutoff = str(datetime.now() - timedelta(hours=hours))
        cursor = await db.execute(
            "SELECT COUNT(*) FROM campaign_fulfillments WHERE dm_sent=1 AND dm_sent_at >= ?",
            (cutoff,),
        )
        row = await cursor.fetchone()
        return row[0]

    async def mark_skipped(self, campaign_id: str, username: str, reason: str):
        """Mark a user as skipped (suspended, private, not_exists, dm_failed)."""
        db = await self._get_conn()
        await db.execute(
            """UPDATE campaign_fulfillments SET skip_reason=?, dm_failed_at=?
               WHERE campaign_id=? AND username=?""",
            (reason, datetime.now(), campaign_id, username),
        )
        await db.commit()

    async def get_fulfillment_count(self, campaign_id: str) -> dict:
        """Get counts of total replies, fulfilled DMs, and skipped for a campaign."""
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN dm_sent=1 THEN 1 ELSE 0 END) as dms_sent,
                 SUM(CASE WHEN skip_reason IS NOT NULL THEN 1 ELSE 0 END) as skipped
               FROM campaign_fulfillments WHERE campaign_id=?""",
            (campaign_id,),
        )
        row = await cursor.fetchone()
        return {"total": row[0], "dms_sent": row[1] or 0, "skipped": row[2] or 0}

    async def mark_fulfilled(self, campaign_id: str, username: str):
        db = await self._get_conn()
        await db.execute(
            """UPDATE campaign_fulfillments SET dm_sent=1, dm_sent_at=?, is_following=1
               WHERE campaign_id=? AND username=?""",
            (datetime.now(), campaign_id, username),
        )
        await db.commit()

    def _row_to_fulfillment(self, row) -> CampaignFulfillment:
        keys = row.keys()
        return CampaignFulfillment(
            id=row["id"], campaign_id=row["campaign_id"],
            username=row["username"], replied_at=row["replied_at"],
            is_following=bool(row["is_following"]), dm_sent=bool(row["dm_sent"]),
            dm_sent_at=row["dm_sent_at"],
            dm_failed_at=row["dm_failed_at"] if "dm_failed_at" in keys else None,
            skip_reason=row["skip_reason"] if "skip_reason" in keys else None,
            created_at=row["created_at"],
        )

    def _row_to_campaign(self, row) -> Campaign:
        return Campaign(
            id=row["id"], campaign_id=row["campaign_id"],
            tweet_text=row["tweet_text"], keyword=row["keyword"],
            download_url=row["download_url"], freebie_name=row["freebie_name"],
            dm_template=row["dm_template"], tweet_url=row["tweet_url"],
            status=row["status"], replies_count=row["replies_count"],
            follows_count=row["follows_count"], dms_sent=row["dms_sent"],
            created_at=row["created_at"],
        )

    # --- Agent Runs ---

    # --- UGC Video Jobs ---

    async def insert_video_job(self, job: dict) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO ugc_video_jobs (job_id, topic, platform, duration, status,
               influencer_key, motion_prompt, voiceover_script, angle_json, run_dir,
               run_params_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["job_id"], job["topic"], job["platform"], job.get("duration", "5"),
                job.get("status", "pending"), job.get("influencer_key"),
                job.get("motion_prompt"), job.get("voiceover_script"),
                job.get("angle_json"), job.get("run_dir"),
                job.get("run_params_json"),
            ),
        )
        await db.commit()
        return cursor.lastrowid

    _ALLOWED_VIDEO_JOB_COLUMNS = {
        "status", "frame_status", "frame_path", "video_status", "video_task_id",
        "video_path", "tts_status", "tts_path", "lipsync_status", "lipsync_task_id",
        "lipsync_path", "assembly_status", "final_path", "error_message",
        "retry_count", "completed_at", "influencer_key", "motion_prompt",
        "voiceover_script", "angle_json", "run_dir", "run_params_json",
    }

    async def update_video_job_step(self, job_id: str, **kwargs):
        """Update specific fields on a video job. Column names are whitelisted."""
        if not kwargs:
            return
        invalid = set(kwargs) - self._ALLOWED_VIDEO_JOB_COLUMNS
        if invalid:
            raise ValueError(f"Invalid column(s) for ugc_video_jobs: {invalid}")
        db = await self._get_conn()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id]
        await db.execute(f"UPDATE ugc_video_jobs SET {sets} WHERE job_id=?", vals)
        await db.commit()

    async def get_video_job(self, job_id: str) -> dict | None:
        db = await self._get_conn()
        cursor = await db.execute("SELECT * FROM ugc_video_jobs WHERE job_id=?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)

    async def get_incomplete_video_jobs(self) -> list[dict]:
        """Get jobs that aren't in any terminal state — for crash recovery."""
        db = await self._get_conn()
        cursor = await db.execute(
            """SELECT * FROM ugc_video_jobs
               WHERE status NOT IN ('complete', 'failed', 'aborted', 'preview_complete')
               ORDER BY started_at ASC""",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Reddit Karma ---

    async def insert_reddit_karma(self, username: str, comment_karma: int, link_karma: int, total_karma: int):
        db = await self._get_conn()
        await db.execute(
            """INSERT INTO reddit_karma_log (username, comment_karma, link_karma, total_karma)
               VALUES (?, ?, ?, ?)""",
            (username, comment_karma, link_karma, total_karma),
        )
        await db.commit()

    async def get_latest_reddit_karma(self, username: str) -> dict | None:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM reddit_karma_log WHERE username=? ORDER BY scraped_at DESC LIMIT 1",
            (username,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "username": row["username"],
            "comment_karma": row["comment_karma"],
            "link_karma": row["link_karma"],
            "total_karma": row["total_karma"],
            "scraped_at": row["scraped_at"],
        }

    async def count_promotional_actions(self, platform: str, days: int = 30) -> dict:
        """Count promotional vs non-promotional posts/comments in the last N days."""
        db = await self._get_conn()
        cutoff = str(datetime.now() - __import__("datetime").timedelta(days=days))
        # Count posts
        cursor = await db.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN is_promotional=1 THEN 1 ELSE 0 END) as promotional
               FROM posts WHERE platform=? AND status='posted' AND created_at >= ?""",
            (platform, cutoff),
        )
        post_row = await cursor.fetchone()
        # Count comments
        cursor = await db.execute(
            """SELECT
                 COUNT(*) as total,
                 SUM(CASE WHEN is_promotional=1 THEN 1 ELSE 0 END) as promotional
               FROM comments WHERE platform=? AND status='posted' AND created_at >= ?""",
            (platform, cutoff),
        )
        comment_row = await cursor.fetchone()
        total = (post_row[0] or 0) + (comment_row[0] or 0)
        promotional = (post_row[1] or 0) + (comment_row[1] or 0)
        return {"total": total, "promotional": promotional, "non_promotional": total - promotional}

    async def get_recent_runs(self, limit: int = 20) -> list[AgentRun]:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            AgentRun(
                id=row["id"], agent=row["agent"], task_type=row["task_type"],
                started_at=row["started_at"], completed_at=row["completed_at"],
                status=row["status"], iterations=row["iterations"],
                error_message=row["error_message"],
                api_tokens_used=row["api_tokens_used"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ── Flash sales (TikTok Shop) ─────────────────────────────

    async def insert_flash_sale(self, sale: FlashSale) -> int:
        db = await self._get_conn()
        cursor = await db.execute(
            """INSERT INTO flash_sales (sale_id, name, product_key, discount_type,
               discount_value, currency, starts_at, ends_at, tiktok_activity_id,
               shop_cipher, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sale.sale_id, sale.name, sale.product_key, sale.discount_type,
                sale.discount_value, sale.currency, sale.starts_at, sale.ends_at,
                sale.tiktok_activity_id, sale.shop_cipher, sale.status,
            ),
        )
        await db.commit()
        return cursor.lastrowid

    async def get_flash_sale(self, sale_id: str) -> FlashSale | None:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM flash_sales WHERE sale_id = ?", (sale_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_flash_sale(row) if row else None

    async def get_flash_sales_by_status(self, status: str) -> list[FlashSale]:
        db = await self._get_conn()
        cursor = await db.execute(
            "SELECT * FROM flash_sales WHERE status = ? ORDER BY starts_at",
            (status,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_flash_sale(r) for r in rows]

    async def get_candidate_live_sales(self, product_key: str | None = None) -> list[FlashSale]:
        """Rows that CLAIM to be live. Liveness is decided by flash_sale_state,
        not by this query — status alone is not proof the deal exists remotely.
        """
        db = await self._get_conn()
        if product_key:
            cursor = await db.execute(
                "SELECT * FROM flash_sales WHERE status = 'live' AND product_key = ? "
                "ORDER BY ends_at",
                (product_key,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM flash_sales WHERE status = 'live' ORDER BY ends_at",
            )
        rows = await cursor.fetchall()
        return [self._row_to_flash_sale(r) for r in rows]

    async def attach_remote_activity(
        self, sale_id: str, tiktok_activity_id: str, shop_cipher: str,
    ):
        """Record that the Flash Deal now exists on TikTok Shop."""
        db = await self._get_conn()
        await db.execute(
            """UPDATE flash_sales
               SET tiktok_activity_id = ?, shop_cipher = ?,
                   remote_synced_at = CURRENT_TIMESTAMP,
                   remote_verified_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE sale_id = ?""",
            (tiktok_activity_id, shop_cipher, sale_id),
        )
        await db.commit()

    async def mark_flash_sale_status(
        self, sale_id: str, status: str, last_error: str | None = None,
    ):
        db = await self._get_conn()
        await db.execute(
            """UPDATE flash_sales
               SET status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
               WHERE sale_id = ?""",
            (status, last_error, sale_id),
        )
        await db.commit()

    async def mark_flash_sale_verified(self, sale_id: str):
        """Stamp a fresh confirmation that the remote deal is still running."""
        db = await self._get_conn()
        await db.execute(
            """UPDATE flash_sales
               SET remote_verified_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE sale_id = ?""",
            (sale_id,),
        )
        await db.commit()

    async def mark_flash_sale_advertised(self, sale_id: str):
        """Record that a caption cited this sale, for parity auditing."""
        db = await self._get_conn()
        await db.execute(
            """UPDATE flash_sales
               SET last_advertised_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE sale_id = ?""",
            (sale_id,),
        )
        await db.commit()

    def _row_to_flash_sale(self, row) -> FlashSale:
        return FlashSale(
            id=row["id"], sale_id=row["sale_id"], name=row["name"],
            product_key=row["product_key"], discount_type=row["discount_type"],
            discount_value=row["discount_value"], currency=row["currency"],
            starts_at=row["starts_at"], ends_at=row["ends_at"],
            tiktok_activity_id=row["tiktok_activity_id"],
            shop_cipher=row["shop_cipher"], status=row["status"],
            remote_verified_at=row["remote_verified_at"],
            remote_synced_at=row["remote_synced_at"],
            last_error=row["last_error"],
            last_advertised_at=row["last_advertised_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

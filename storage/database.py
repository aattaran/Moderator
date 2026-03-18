"""Async SQLite database wrapper with WAL mode."""

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from storage.models import AgentRun, Comment, Post, TargetAccount, WeightEntry

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
            """INSERT INTO posts (platform, content, content_style, media_urls,
               posted_at, status, engagement_likes, engagement_reposts,
               engagement_replies, engagement_views)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post.platform, post.content, post.content_style,
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
            media_urls=json.loads(row["media_urls"]) if row["media_urls"] else [],
            posted_at=row["posted_at"], status=row["status"],
            engagement_likes=row["engagement_likes"],
            engagement_reposts=row["engagement_reposts"],
            engagement_replies=row["engagement_replies"],
            engagement_views=row["engagement_views"],
            scraped_at=row["scraped_at"], created_at=row["created_at"],
        )

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

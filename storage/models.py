"""Data models for the Moderator system."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    platform: str
    content: str
    content_style: str
    media_urls: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    status: str = "draft"  # draft, pending_approval, posted, failed
    engagement_likes: int = 0
    engagement_reposts: int = 0
    engagement_replies: int = 0
    engagement_views: int = 0
    scraped_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Comment:
    platform: str
    target_post_url: str
    target_author: str
    content: str
    comment_style: str
    topic: str
    posted_at: datetime | None = None
    status: str = "draft"  # draft, pending_approval, posted, failed
    engagement_likes: int = 0
    engagement_replies: int = 0
    scraped_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class TargetAccount:
    platform: str
    username: str
    follower_count: int = 0
    avg_engagement_rate: float = 0.0
    relevance_score: float = 0.5
    last_checked: datetime | None = None
    active: bool = True
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class WeightEntry:
    category: str  # content_style, comment_style, topic
    name: str
    weight: float = 1.0
    period_start: datetime | None = None
    period_end: datetime | None = None
    sample_count: int = 0
    avg_engagement: float = 0.0
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class AgentRun:
    agent: str
    task_type: str  # post, engage, scrape, evaluate
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "running"  # running, success, failed, timeout
    iterations: int = 0
    error_message: str | None = None
    api_tokens_used: int = 0
    id: int | None = None
    created_at: datetime | None = None

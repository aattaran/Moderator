"""Data models for the Moderator system."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Post:
    platform: str
    content: str
    content_style: str
    media_urls: list[str] = field(default_factory=list)
    topic: str | None = None
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
class StyleGuideline:
    version: int
    guidelines_text: str
    analysis_summary: str
    platform: str = "x"
    top_patterns: list[str] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    posts_analyzed: int = 0
    avg_engagement_score: float = 0.0
    active: bool = True
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Campaign:
    campaign_id: str
    tweet_text: str
    keyword: str
    download_url: str
    freebie_name: str = ""
    dm_template: str = ""
    tweet_url: str | None = None
    status: str = "draft"  # draft, active, paused, completed
    replies_count: int = 0
    follows_count: int = 0
    dms_sent: int = 0
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class CampaignFulfillment:
    campaign_id: str
    username: str
    replied_at: datetime | None = None
    is_following: bool = False
    dm_sent: bool = False
    dm_sent_at: datetime | None = None
    dm_failed_at: datetime | None = None
    skip_reason: str | None = None  # "suspended", "not_exists", "private", "dm_failed"
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


@dataclass
class FlashSale:
    """A TikTok Shop Flash Deal activity, local-side.

    `tiktok_activity_id` stays None until the deal actually exists on TikTok
    Shop — a row without it is a plan, not a sale, and must never be advertised.
    See core/flash_sale_state.py for the liveness rules.
    """

    sale_id: str
    name: str
    product_key: str
    discount_type: str  # percentage | fixed_amount
    discount_value: float
    starts_at: datetime
    ends_at: datetime
    currency: str = "USD"
    tiktok_activity_id: str | None = None
    shop_cipher: str | None = None
    status: str = "draft"  # draft, scheduled, live, ended, failed, aborted
    remote_verified_at: datetime | None = None
    remote_synced_at: datetime | None = None
    last_error: str | None = None
    last_advertised_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

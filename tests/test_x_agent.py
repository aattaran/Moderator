"""Tests for the X (Twitter) agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.x_agent import XAgent
from storage.models import Post


class FakeSettings:
    ANTHROPIC_API_KEY = "test-key"
    MODEL = "claude-opus-4-6"
    PLATFORM = "x"
    POSTS_PER_DAY = 3
    MAX_POSTS_PER_DAY = 10
    FACEBOOK_POSTS_PER_DAY = 3
    TIKTOK_POSTS_PER_DAY = 2
    MAX_COMMENTS_PER_HOUR = 10
    REQUIRE_APPROVAL = False
    DRY_RUN = True
    DISPLAY_WIDTH = 1024
    DISPLAY_HEIGHT = 768
    BROWSER_PROFILE_PATH = "/tmp/test-profile"
    DB_PATH = ":memory:"


@pytest.mark.asyncio
async def test_get_platform_name(db):
    config = FakeSettings()
    agent = XAgent(MagicMock(), db, config)
    assert agent.get_platform_name() == "x"


@pytest.mark.asyncio
async def test_post_content_success(db):
    config = FakeSettings()

    with patch("core.x_actions.XActions.compose_and_post", new_callable=AsyncMock, return_value=True):
        agent = XAgent(MagicMock(), db, config)
        post = await agent.post_content("Hello world!", "hot_take", "ai")

    assert post.status == "posted"
    assert post.content == "Hello world!"
    assert post.content_style == "hot_take"
    assert post.posted_at is not None


@pytest.mark.asyncio
async def test_post_content_failure(db):
    config = FakeSettings()

    with patch("core.x_actions.XActions.compose_and_post", new_callable=AsyncMock, return_value=False):
        agent = XAgent(MagicMock(), db, config)
        post = await agent.post_content("Test post", "question", "tech")

    assert post.status == "failed"


@pytest.mark.asyncio
async def test_post_content_rate_limited(db):
    config = FakeSettings()
    config.POSTS_PER_DAY = 0  # No posts allowed for X platform

    from agents.base_agent import RateLimitError
    with pytest.raises(RateLimitError):
        agent = XAgent(MagicMock(), db, config)
        await agent.post_content("Should fail", "insight", "ai")


@pytest.mark.asyncio
async def test_engage_success(db):
    config = FakeSettings()

    with patch("core.x_actions.XActions.reply_to_latest_post", new_callable=AsyncMock, return_value=True):
        agent = XAgent(MagicMock(), db, config)
        comment = await agent.engage("testuser", "Great post!", "agree_and_extend", "ai")

    assert comment.target_author == "testuser"
    assert comment.content == "Great post!"
    assert comment.comment_style == "agree_and_extend"

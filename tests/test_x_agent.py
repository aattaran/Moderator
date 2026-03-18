"""Tests for the X (Twitter) agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.x_agent import XAgent
from core.computer_use import AgentLoop, AgentLoopResult
from storage.models import Post


class FakeSettings:
    ANTHROPIC_API_KEY = "test-key"
    MODEL = "claude-opus-4-6"
    PLATFORM = "x"
    MAX_POSTS_PER_DAY = 10
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
    agent_loop = MagicMock(spec=AgentLoop)
    agent = XAgent(agent_loop, db, config)
    assert agent.get_platform_name() == "x"


@pytest.mark.asyncio
async def test_post_content_success(db):
    config = FakeSettings()
    agent_loop = AsyncMock(spec=AgentLoop)
    agent_loop.run.return_value = AgentLoopResult(
        success=True, iterations=5,
        total_input_tokens=1000, total_output_tokens=200,
        final_text="Posted successfully",
    )

    agent = XAgent(agent_loop, db, config)
    post = await agent.post_content("Hello world!", "hot_take", "ai")

    assert post.status == "posted"
    assert post.content == "Hello world!"
    assert post.content_style == "hot_take"
    assert post.posted_at is not None
    agent_loop.run.assert_called_once()


@pytest.mark.asyncio
async def test_post_content_failure(db):
    config = FakeSettings()
    agent_loop = AsyncMock(spec=AgentLoop)
    agent_loop.run.return_value = AgentLoopResult(
        success=False, iterations=20,
        total_input_tokens=5000, total_output_tokens=1000,
    )

    agent = XAgent(agent_loop, db, config)
    post = await agent.post_content("Test post", "question", "tech")

    assert post.status == "failed"


@pytest.mark.asyncio
async def test_post_content_rate_limited(db):
    config = FakeSettings()
    config.MAX_POSTS_PER_DAY = 0  # No posts allowed

    agent_loop = AsyncMock(spec=AgentLoop)
    agent = XAgent(agent_loop, db, config)

    from agents.base_agent import RateLimitError
    with pytest.raises(RateLimitError):
        await agent.post_content("Should fail", "insight", "ai")


@pytest.mark.asyncio
async def test_engage_success(db):
    config = FakeSettings()
    agent_loop = AsyncMock(spec=AgentLoop)
    agent_loop.run.return_value = AgentLoopResult(
        success=True, iterations=8,
        total_input_tokens=2000, total_output_tokens=400,
    )

    agent = XAgent(agent_loop, db, config)
    comment = await agent.engage("testuser", "Great post!", "agree_and_extend", "ai")

    assert comment.target_author == "testuser"
    assert comment.content == "Great post!"
    assert comment.comment_style == "agree_and_extend"


@pytest.mark.asyncio
async def test_parse_metrics_response():
    """Test JSON parsing from Claude's metrics response."""
    response_text = """
    Here are the metrics I found:
    ```json
    [
        {"text": "Hello world post...", "likes": 42, "reposts": 5, "replies": 12, "views": 1500},
        {"text": "Another tweet...", "likes": 100, "reposts": 20, "replies": 8, "views": 5000}
    ]
    ```
    """
    metrics = XAgent._parse_metrics_response(response_text)
    assert len(metrics) == 2
    assert metrics[0]["likes"] == 42
    assert metrics[1]["views"] == 5000


@pytest.mark.asyncio
async def test_parse_metrics_invalid_json():
    """Should return empty list on invalid JSON."""
    metrics = XAgent._parse_metrics_response("No JSON here")
    assert metrics == []

"""Tests for the SQLite database layer."""

import pytest
from datetime import datetime

from storage.database import Database
from storage.models import AgentRun, Comment, Post, TargetAccount, WeightEntry


@pytest.mark.asyncio
async def test_insert_and_get_post(db):
    post = Post(
        platform="x",
        content="Hello world!",
        content_style="hot_take",
        status="posted",
        posted_at=datetime.now(),
    )
    post_id = await db.insert_post(post)
    assert post_id > 0

    posts = await db.get_recent_posts("x", limit=10)
    assert len(posts) == 1
    assert posts[0].content == "Hello world!"
    assert posts[0].content_style == "hot_take"


@pytest.mark.asyncio
async def test_count_posts_today(db):
    # Insert 3 posts for today
    for i in range(3):
        post = Post(
            platform="x",
            content=f"Post {i}",
            content_style="insight",
            status="posted",
            posted_at=datetime.now(),
        )
        await db.insert_post(post)

    count = await db.count_posts_today("x")
    assert count == 3


@pytest.mark.asyncio
async def test_update_post_engagement(db):
    post = Post(platform="x", content="Test", content_style="question", status="posted")
    post_id = await db.insert_post(post)

    await db.update_post_engagement(post_id, likes=10, reposts=3, replies=5, views=200)

    posts = await db.get_recent_posts("x", limit=1)
    assert posts[0].engagement_likes == 10
    assert posts[0].engagement_reposts == 3
    assert posts[0].engagement_replies == 5
    assert posts[0].engagement_views == 200
    assert posts[0].scraped_at is not None


@pytest.mark.asyncio
async def test_insert_comment(db):
    comment = Comment(
        platform="x",
        target_post_url="https://x.com/user/status/123",
        target_author="testuser",
        content="Great point!",
        comment_style="agree_and_extend",
        topic="ai",
        status="posted",
        posted_at=datetime.now(),
    )
    comment_id = await db.insert_comment(comment)
    assert comment_id > 0


@pytest.mark.asyncio
async def test_count_comments_last_hour(db):
    for i in range(5):
        comment = Comment(
            platform="x",
            target_post_url=f"https://x.com/user/status/{i}",
            target_author="user",
            content=f"Comment {i}",
            comment_style="question",
            topic="tech",
            status="posted",
            posted_at=datetime.now(),
        )
        await db.insert_comment(comment)

    count = await db.count_comments_last_hour("x")
    assert count == 5


@pytest.mark.asyncio
async def test_upsert_target_account(db):
    account = TargetAccount(
        platform="x",
        username="elonmusk",
        follower_count=100000,
        avg_engagement_rate=0.05,
        relevance_score=0.8,
        last_checked=datetime.now(),
    )
    account_id = await db.upsert_target_account(account)
    assert account_id > 0

    # Upsert same account with updated data
    account.follower_count = 150000
    await db.upsert_target_account(account)

    targets = await db.get_active_targets("x")
    assert len(targets) == 1
    assert targets[0].follower_count == 150000


@pytest.mark.asyncio
async def test_weight_entries(db):
    # Initialize weights
    await db.initialize_weights("content_style", ["hot_take", "thread", "question"], datetime.now())

    weights = await db.get_current_weights("content_style")
    assert len(weights) == 3
    assert all(w.weight == 1.0 for w in weights)

    # Update a weight
    weights[0].weight = 1.5
    await db.upsert_weight_entry(weights[0])

    updated = await db.get_current_weights("content_style")
    hot_take = next(w for w in updated if w.name == "hot_take")
    assert hot_take.weight == 1.5


@pytest.mark.asyncio
async def test_agent_run_lifecycle(db):
    run = AgentRun(agent="x", task_type="post", started_at=datetime.now())
    run_id = await db.log_agent_run(run)
    assert run_id > 0

    await db.complete_agent_run(
        run_id, status="success", iterations=10, api_tokens_used=5000
    )

    runs = await db.get_recent_runs(limit=1)
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].iterations == 10
    assert runs[0].api_tokens_used == 5000
    assert runs[0].completed_at is not None


@pytest.mark.asyncio
async def test_idempotent_initialization(db):
    """initialize_weights should not duplicate if called twice."""
    await db.initialize_weights("topic", ["ai", "tech"], datetime.now())
    await db.initialize_weights("topic", ["ai", "tech"], datetime.now())

    weights = await db.get_current_weights("topic")
    assert len(weights) == 2

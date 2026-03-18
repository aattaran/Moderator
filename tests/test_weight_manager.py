"""Tests for the adaptive weight scoring system."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from storage.database import Database
from storage.models import Post, WeightEntry
from strategies.weight_manager import WeightManager


class FakeSettings:
    """Minimal settings for testing."""
    WEIGHT_EVAL_PERIOD_DAYS = 14
    LEARNING_RATE = 0.1
    MIN_WEIGHT_FLOOR = 0.05


@pytest.mark.asyncio
async def test_select_returns_valid_option(db):
    """select() should return one of the seeded options."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    await db.initialize_weights("content_style", ["hot_take", "thread", "question"], datetime.now())

    for _ in range(20):
        choice = await wm.select("content_style")
        assert choice in ["hot_take", "thread", "question"]


@pytest.mark.asyncio
async def test_select_respects_weights(db):
    """Higher-weighted options should be selected more often."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    now = datetime.now()
    await db.initialize_weights("test_cat", ["a", "b"], now)

    # Set weight of 'a' much higher
    weights = await db.get_current_weights("test_cat")
    for w in weights:
        if w.name == "a":
            w.weight = 9.0
        else:
            w.weight = 1.0
        await db.upsert_weight_entry(w)

    counts = {"a": 0, "b": 0}
    for _ in range(200):
        choice = await wm.select("test_cat")
        counts[choice] += 1

    # 'a' should be selected much more often
    assert counts["a"] > counts["b"] * 3


@pytest.mark.asyncio
async def test_select_fallback_on_empty_db(db):
    """select() should fall back to defaults when DB is empty."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    choice = await wm.select("content_style")
    assert choice in ["hot_take", "thread", "question", "insight", "meme_caption"]


@pytest.mark.asyncio
async def test_evaluate_period_adjusts_weights(db):
    """evaluate_period should increase weight of high-performing options."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    now = datetime.now()
    await db.initialize_weights("content_style", ["hot_take", "thread"], now)

    # Create posts with different engagement levels
    for i in range(5):
        post = Post(
            platform="x", content=f"Hot take {i}", content_style="hot_take",
            status="posted", posted_at=now - timedelta(days=1),
            engagement_likes=100, engagement_reposts=20, engagement_replies=10,
        )
        await db.insert_post(post)

    for i in range(5):
        post = Post(
            platform="x", content=f"Thread {i}", content_style="thread",
            status="posted", posted_at=now - timedelta(days=1),
            engagement_likes=10, engagement_reposts=2, engagement_replies=1,
        )
        await db.insert_post(post)

    # Run evaluation
    await wm.evaluate_period("content_style", "x")

    weights = await db.get_current_weights("content_style")
    hot_take_weight = next(w for w in weights if w.name == "hot_take")
    thread_weight = next(w for w in weights if w.name == "thread")

    # hot_take should have higher weight (more engagement)
    assert hot_take_weight.weight > thread_weight.weight


@pytest.mark.asyncio
async def test_weight_floor_enforced(db):
    """Weights should never drop below MIN_WEIGHT_FLOOR."""
    config = FakeSettings()
    config.LEARNING_RATE = 10.0  # Aggressive learning rate
    wm = WeightManager(db, config)

    now = datetime.now()
    await db.initialize_weights("content_style", ["good", "bad"], now)

    # Good gets lots of engagement, bad gets none
    for i in range(5):
        await db.insert_post(Post(
            platform="x", content=f"Good {i}", content_style="good",
            status="posted", posted_at=now - timedelta(days=1),
            engagement_likes=1000, engagement_reposts=100, engagement_replies=50,
        ))
    for i in range(5):
        await db.insert_post(Post(
            platform="x", content=f"Bad {i}", content_style="bad",
            status="posted", posted_at=now - timedelta(days=1),
            engagement_likes=0, engagement_reposts=0, engagement_replies=0,
        ))

    await wm.evaluate_period("content_style", "x")

    weights = await db.get_current_weights("content_style")
    bad_weight = next(w for w in weights if w.name == "bad")
    assert bad_weight.weight >= config.MIN_WEIGHT_FLOOR


@pytest.mark.asyncio
async def test_normalization_preserves_sum(db):
    """After evaluation, weights should sum to len(options)."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    now = datetime.now()
    options = ["a", "b", "c"]
    await db.initialize_weights("test_norm", options, now)

    for name in options:
        for i in range(3):
            await db.insert_post(Post(
                platform="x", content=f"{name} {i}", content_style=name,
                status="posted", posted_at=now - timedelta(days=1),
                engagement_likes=10 * (ord(name) - ord('a') + 1),
                engagement_reposts=0, engagement_replies=0,
            ))

    await wm.evaluate_period("test_norm", "x")

    weights = await db.get_current_weights("test_norm")
    total = sum(w.weight for w in weights)
    assert abs(total - len(options)) < 0.01  # Should sum to 3


@pytest.mark.asyncio
async def test_insufficient_samples_skipped(db):
    """Options with fewer than 3 samples should not be adjusted."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    now = datetime.now()
    await db.initialize_weights("content_style", ["popular", "rare"], now)

    # popular has 5 posts, rare has only 1
    for i in range(5):
        await db.insert_post(Post(
            platform="x", content=f"Popular {i}", content_style="popular",
            status="posted", posted_at=now - timedelta(days=1),
            engagement_likes=50,
        ))
    await db.insert_post(Post(
        platform="x", content="Rare 1", content_style="rare",
        status="posted", posted_at=now - timedelta(days=1),
        engagement_likes=200,  # High engagement but too few samples
    ))

    # Should not adjust because only 1 option has enough samples
    await wm.evaluate_period("content_style", "x")

    weights = await db.get_current_weights("content_style")
    # Both should still be at default since there's not enough data to compare
    for w in weights:
        assert w.weight == 1.0


@pytest.mark.asyncio
async def test_get_weights_summary(db):
    """get_weights_summary should return a clean dict."""
    config = FakeSettings()
    wm = WeightManager(db, config)

    await db.initialize_weights("topic", ["ai", "tech"], datetime.now())

    summary = await wm.get_weights_summary("topic")
    assert summary == {"ai": 1.0, "tech": 1.0}

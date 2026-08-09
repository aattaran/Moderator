"""Tests for TikTok post-once video rotation.

These target the guarantee that matters on a brand account: every video in the
library goes out before any video goes out twice.
"""

import os
from datetime import datetime, timedelta

import pytest

from agents import tiktok_agent as tt_mod
from agents.tiktok_agent import TikTokAgent
from config import Settings
from storage.models import Post


@pytest.fixture
def video_dir(tmp_path, monkeypatch):
    """A library of 5 videos, two operator-tagged 'good'."""
    names = ["a_plain.mp4", "b_good.mp4", "c_plain.mp4", "d_great.mp4", "e_plain.mp4"]
    for n in names:
        (tmp_path / n).write_bytes(b"\x00")
    monkeypatch.setattr(tt_mod, "PRODUCT_VIDEOS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def agent(db, video_dir):
    # No proxy configured -> TikTokActions is constructed but never started.
    return TikTokAgent(db, Settings(GEMINI_API_KEY="test-key"))


async def _mark_posted(db, filename, when):
    await db.insert_post(Post(
        platform="tiktok", content="c", content_style="s",
        status="posted", posted_at=when, media_urls=[filename],
    ))


@pytest.mark.asyncio
async def test_prefers_tagged_takes_when_nothing_posted(agent):
    """With an untouched library, a good/great take goes first."""
    pick = os.path.basename(await agent._pick_next_video())
    assert pick in {"b_good.mp4", "d_great.mp4"}


@pytest.mark.asyncio
async def test_never_repeats_until_library_exhausted(agent, db, video_dir):
    """The core guarantee: 5 picks cover all 5 videos, no duplicates."""
    seen = []
    for i in range(5):
        pick = os.path.basename(await agent._pick_next_video())
        assert pick not in seen, f"repeated {pick} before exhausting library: {seen}"
        seen.append(pick)
        await _mark_posted(db, pick, datetime.now() + timedelta(minutes=i))

    assert sorted(seen) == sorted(os.listdir(video_dir))


@pytest.mark.asyncio
async def test_cycles_to_least_recently_posted_when_exhausted(agent, db):
    """After every video has posted, the oldest one comes back — not the same file forever."""
    base = datetime(2026, 1, 1, 12, 0, 0)
    order = ["a_plain.mp4", "b_good.mp4", "c_plain.mp4", "d_great.mp4", "e_plain.mp4"]
    for i, name in enumerate(order):
        await _mark_posted(db, name, base + timedelta(hours=i))

    # a_plain is the least recently posted, so it must come back first.
    assert os.path.basename(await agent._pick_next_video()) == "a_plain.mp4"

    # Post it again; the next-oldest must follow rather than a_plain repeating.
    await _mark_posted(db, "a_plain.mp4", base + timedelta(hours=10))
    assert os.path.basename(await agent._pick_next_video()) == "b_good.mp4"


@pytest.mark.asyncio
async def test_failed_posts_do_not_consume_a_video(agent, db):
    """A failed attempt must not burn the video — it should be retried later."""
    await db.insert_post(Post(
        platform="tiktok", content="c", content_style="s",
        status="failed", media_urls=["b_good.mp4"],
    ))
    # b_good is still unposted, so it remains eligible.
    assert os.path.basename(await agent._pick_next_video()) in {"b_good.mp4", "d_great.mp4"}


@pytest.mark.asyncio
async def test_other_platforms_do_not_consume_tiktok_videos(agent, db):
    """An Instagram post of the same file must not mark it used for TikTok."""
    await db.insert_post(Post(
        platform="instagram", content="c", content_style="s",
        status="posted", posted_at=datetime.now(), media_urls=["b_good.mp4"],
    ))
    assert os.path.basename(await agent._pick_next_video()) in {"b_good.mp4", "d_great.mp4"}


@pytest.mark.asyncio
async def test_returns_none_on_empty_library(db, tmp_path, monkeypatch):
    monkeypatch.setattr(tt_mod, "PRODUCT_VIDEOS_DIR", str(tmp_path / "empty"))
    agent = TikTokAgent(db, Settings(GEMINI_API_KEY="test-key"))
    assert await agent._pick_next_video() is None

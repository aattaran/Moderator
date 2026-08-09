"""Tests for flash-sale liveness.

These are written to BREAK the predicate, not to confirm it. The failure that
matters is a false positive: advertising a discount the shop isn't charging.
So every test below that expects False is guarding a real way a caption could
lie to a customer.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.flash_sale_state import (
    DEFAULT_MAX_STALENESS_SECONDS,
    describe_discount,
    evaluate_liveness,
    get_live_sale,
    time_remaining,
)
from storage.models import FlashSale

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def make_sale(**overrides) -> FlashSale:
    """A sale that IS live. Each test breaks exactly one thing."""
    defaults = dict(
        sale_id="fs_1",
        name="Weekend Flash",
        product_key="elemnt_core",
        discount_type="percentage",
        discount_value=25,
        starts_at=NOW - timedelta(hours=1),
        ends_at=NOW + timedelta(hours=5),
        tiktok_activity_id="7abc123",
        shop_cipher="CIPHER",
        status="live",
        remote_verified_at=NOW - timedelta(seconds=60),
    )
    defaults.update(overrides)
    return FlashSale(**defaults)


def test_baseline_is_live():
    """Guard the fixture itself — if this fails the other tests prove nothing."""
    assert evaluate_liveness(make_sale(), now=NOW).is_live


# ── The two that actually prevent lying to customers ──────────────────


def test_not_live_without_remote_activity_id():
    """A row can be written 'live' and then creation fails. It is a plan, not a sale."""
    result = evaluate_liveness(make_sale(tiktok_activity_id=None), now=NOW)
    assert not result.is_live
    assert "never created" in result.reason


def test_not_live_when_confirmation_is_stale():
    """Ended by hand in Seller Center: status stays 'live', reality doesn't."""
    stale = NOW - timedelta(seconds=DEFAULT_MAX_STALENESS_SECONDS + 1)
    result = evaluate_liveness(make_sale(remote_verified_at=stale), now=NOW)
    assert not result.is_live
    assert "old" in result.reason


def test_not_live_when_never_confirmed():
    result = evaluate_liveness(make_sale(remote_verified_at=None), now=NOW)
    assert not result.is_live
    assert "never confirmed" in result.reason


def test_staleness_boundary_is_inclusive():
    """Exactly at the limit is still live; one second past is not."""
    at_limit = NOW - timedelta(seconds=DEFAULT_MAX_STALENESS_SECONDS)
    assert evaluate_liveness(make_sale(remote_verified_at=at_limit), now=NOW).is_live

    past = NOW - timedelta(seconds=DEFAULT_MAX_STALENESS_SECONDS + 1)
    assert not evaluate_liveness(make_sale(remote_verified_at=past), now=NOW).is_live


def test_future_confirmation_rejected_as_clock_skew():
    """A future timestamp would otherwise never go stale — an unbounded lie."""
    future = NOW + timedelta(hours=2)
    result = evaluate_liveness(make_sale(remote_verified_at=future), now=NOW)
    assert not result.is_live
    assert "skew" in result.reason


# ── Window and status ─────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["draft", "scheduled", "ended", "failed", "aborted"])
def test_non_live_statuses_never_advertise(status):
    assert not evaluate_liveness(make_sale(status=status), now=NOW).is_live


def test_not_live_before_window_opens():
    sale = make_sale(starts_at=NOW + timedelta(hours=1), ends_at=NOW + timedelta(hours=9))
    assert not evaluate_liveness(sale, now=NOW).is_live


def test_not_live_after_window_closes():
    sale = make_sale(starts_at=NOW - timedelta(hours=9), ends_at=NOW - timedelta(hours=1))
    assert not evaluate_liveness(sale, now=NOW).is_live


def test_window_end_is_exclusive():
    """At exactly ends_at the sale is over — countdown hit zero."""
    sale = make_sale(ends_at=NOW)
    assert not evaluate_liveness(sale, now=NOW).is_live


def test_window_start_is_inclusive():
    sale = make_sale(starts_at=NOW)
    assert evaluate_liveness(sale, now=NOW).is_live


# ── Hostile timestamp formats ─────────────────────────────────────────


def test_sqlite_string_timestamps_are_accepted():
    """aiosqlite hands back TEXT, not datetime. The real read path must work."""
    sale = make_sale(
        starts_at="2026-08-08 11:00:00",
        ends_at="2026-08-08 17:00:00",
        remote_verified_at="2026-08-08 11:59:00",
    )
    assert evaluate_liveness(sale, now=NOW).is_live


def test_unparseable_window_fails_closed():
    sale = make_sale(starts_at="not a date", ends_at="also not a date")
    result = evaluate_liveness(sale, now=NOW)
    assert not result.is_live
    assert "unparseable" in result.reason


def test_empty_string_timestamp_fails_closed():
    assert not evaluate_liveness(make_sale(remote_verified_at=""), now=NOW).is_live


def test_naive_now_argument_is_utc_not_host_local():
    """Regression: `now` used to go through .astimezone(), which reads a naive
    value as HOST-LOCAL while stored columns are read as UTC. On a non-UTC host
    that shifted the window by the UTC offset — and in one direction kept an
    ENDED sale advertisable. Both sides must interpret naive as UTC.
    """
    naive_utc_now = NOW.replace(tzinfo=None)

    # Sale ended one minute ago. Must be dead regardless of host timezone.
    ended = make_sale(
        starts_at=NOW - timedelta(hours=5), ends_at=NOW - timedelta(minutes=1),
    )
    assert not evaluate_liveness(ended, now=naive_utc_now).is_live

    # And an actually-live sale must still read live with a naive `now`.
    assert evaluate_liveness(make_sale(), now=naive_utc_now).is_live

    # Naive and aware forms of the same instant must agree exactly.
    for sale in (make_sale(), ended, make_sale(status="draft")):
        assert (
            evaluate_liveness(sale, now=naive_utc_now).is_live
            == evaluate_liveness(sale, now=NOW).is_live
        )


def test_naive_now_matches_aware_for_time_remaining():
    naive_utc_now = NOW.replace(tzinfo=None)
    sale = make_sale(ends_at=NOW + timedelta(hours=3))
    assert time_remaining(sale, now=naive_utc_now) == time_remaining(sale, now=NOW)


def test_naive_datetimes_treated_as_utc_not_local():
    """A naive value must not shift by the host's timezone — that would move the
    window by hours on a droplet in a different zone than the laptop."""
    sale = make_sale(
        starts_at=datetime(2026, 8, 8, 11, 0, 0),
        ends_at=datetime(2026, 8, 8, 17, 0, 0),
        remote_verified_at=datetime(2026, 8, 8, 11, 59, 0),
    )
    assert evaluate_liveness(sale, now=NOW).is_live


# ── Rendering ─────────────────────────────────────────────────────────


def test_percentage_renders_without_trailing_zero():
    assert describe_discount(make_sale(discount_type="percentage", discount_value=25)) == "25% off"
    assert describe_discount(make_sale(discount_type="percentage", discount_value=25.0)) == "25% off"


def test_fixed_amount_renders_currency():
    sale = make_sale(discount_type="fixed_amount", discount_value=5, currency="USD")
    assert describe_discount(sale) == "$5.00 off"


def test_unknown_discount_type_degrades_safely():
    """Never invent a number for a shape we don't understand."""
    text = describe_discount(make_sale(discount_type="mystery"))
    assert text == "on sale"
    assert "%" not in text and "$" not in text


def test_time_remaining_none_when_ended():
    assert time_remaining(make_sale(ends_at=NOW - timedelta(minutes=1)), now=NOW) is None


def test_time_remaining_counts_down():
    assert time_remaining(make_sale(ends_at=NOW + timedelta(hours=2)), now=NOW) == timedelta(hours=2)


# ── get_live_sale selection ───────────────────────────────────────────


class FakeDB:
    def __init__(self, sales):
        self._sales = sales
        self.asked_for = None

    async def get_candidate_live_sales(self, product_key=None):
        self.asked_for = product_key
        return list(self._sales)


@pytest.mark.asyncio
async def test_get_live_sale_returns_none_when_no_candidates():
    assert await get_live_sale(FakeDB([]), now=NOW) is None


@pytest.mark.asyncio
async def test_get_live_sale_filters_out_unproven_rows():
    """Rows claiming 'live' but never created remotely must not surface."""
    db = FakeDB([make_sale(sale_id="ghost", tiktok_activity_id=None)])
    assert await get_live_sale(db, now=NOW) is None


@pytest.mark.asyncio
async def test_get_live_sale_prefers_soonest_ending():
    db = FakeDB([
        make_sale(sale_id="later", ends_at=NOW + timedelta(hours=10)),
        make_sale(sale_id="sooner", ends_at=NOW + timedelta(hours=2)),
    ])
    picked = await get_live_sale(db, now=NOW)
    assert picked is not None and picked.sale_id == "sooner"


@pytest.mark.asyncio
async def test_get_live_sale_skips_dead_and_returns_the_valid_one():
    db = FakeDB([
        make_sale(sale_id="dead", tiktok_activity_id=None, ends_at=NOW + timedelta(hours=1)),
        make_sale(sale_id="good", ends_at=NOW + timedelta(hours=4)),
    ])
    picked = await get_live_sale(db, now=NOW)
    assert picked is not None and picked.sale_id == "good"


@pytest.mark.asyncio
async def test_product_key_is_passed_through():
    db = FakeDB([])
    await get_live_sale(db, product_key="elemnt_core", now=NOW)
    assert db.asked_for == "elemnt_core"

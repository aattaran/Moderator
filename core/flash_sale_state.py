"""Authoritative answer to: is a flash sale live RIGHT NOW?

This is the seam between the commerce layer and the content layer. Captions must
call `get_live_sale()` and cite a sale only if it returns one. Never hardcode a
discount into a caption — a post outlives the sale that justified it.

The rule is fail-closed: anything unknown, stale, or unproven reads as "no sale".
A false negative posts a normal caption. A false positive advertises a discount
the shop isn't charging, to real customers.

Four independent conditions, all required:

  1. status == 'live'              — we intended it to be running
  2. tiktok_activity_id is set     — it actually exists on TikTok Shop, not just planned
  3. now is inside [starts_at, ends_at)
  4. remote_verified_at is fresh   — we confirmed recently that it's STILL running

(2) and (4) are the ones that matter. A row can be locally 'live' while the deal
was never created (creation failed after the row was written), or while it was
ended by hand in Seller Center. Status alone proves neither.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from storage.database import Database
from storage.models import FlashSale

logger = logging.getLogger(__name__)

# How old a remote confirmation may be before the sale stops being advertisable.
# Tighter than a typical flash sale so a hand-ended deal falls out of captions
# quickly. Raising this widens the window in which a dead sale can be advertised.
DEFAULT_MAX_STALENESS_SECONDS = 900  # 15 minutes


@dataclass(frozen=True)
class LivenessResult:
    """Why a sale was or wasn't advertisable. `reason` is for logging."""

    is_live: bool
    reason: str


def _as_utc(value) -> datetime | None:
    """Coerce a SQLite TIMESTAMP (str or datetime) to an aware UTC datetime.

    SQLite has no datetime type, so these come back as strings via aiosqlite
    unless a converter is registered. Returns None on anything unparseable —
    which fails closed at the call site rather than raising mid-caption.

    Naive values are read as UTC, never as host-local. Every timestamp entering
    this module — stored columns AND a caller-supplied `now` — goes through here,
    so a naive `datetime.utcnow()` cannot silently shift the sale window by the
    host's UTC offset. That shift was a real bug: it would read as "no sale" on
    one machine and, in the other direction, keep advertising an ended sale.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        # SQLite CURRENT_TIMESTAMP renders as "YYYY-MM-DD HH:MM:SS" (UTC).
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            logger.warning("flash_sale: unparseable timestamp %r", value)
            return None
    # Naive values are UTC by construction (CURRENT_TIMESTAMP is UTC).
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def evaluate_liveness(
    sale: FlashSale,
    now: datetime | None = None,
    max_staleness_seconds: int = DEFAULT_MAX_STALENESS_SECONDS,
) -> LivenessResult:
    """Pure predicate — no I/O, so it is directly unit-testable."""
    now = _as_utc(now) or datetime.now(timezone.utc)

    if sale.status != "live":
        return LivenessResult(False, f"status={sale.status!r}, not 'live'")

    if not sale.tiktok_activity_id:
        return LivenessResult(
            False, "no tiktok_activity_id — deal was never created on TikTok Shop",
        )

    starts_at = _as_utc(sale.starts_at)
    ends_at = _as_utc(sale.ends_at)
    if starts_at is None or ends_at is None:
        return LivenessResult(False, "unparseable sale window")

    if now < starts_at:
        return LivenessResult(False, f"has not started (starts {starts_at.isoformat()})")
    if now >= ends_at:
        return LivenessResult(False, f"already ended (ended {ends_at.isoformat()})")

    verified_at = _as_utc(sale.remote_verified_at)
    if verified_at is None:
        return LivenessResult(False, "never confirmed against TikTok Shop")

    age = (now - verified_at).total_seconds()
    if age > max_staleness_seconds:
        return LivenessResult(
            False,
            f"remote confirmation is {int(age)}s old "
            f"(max {max_staleness_seconds}s) — may have been ended in Seller Center",
        )
    # A confirmation timestamped in the future means clock skew or a bad write;
    # trusting it would extend the staleness window arbitrarily.
    if age < -60:
        return LivenessResult(False, "remote_verified_at is in the future — clock skew")

    return LivenessResult(True, "live")


async def get_live_sale(
    db: Database,
    product_key: str | None = None,
    now: datetime | None = None,
    max_staleness_seconds: int = DEFAULT_MAX_STALENESS_SECONDS,
) -> FlashSale | None:
    """The only sanctioned way for content code to learn about a live sale.

    Returns the soonest-ending live sale, or None. When several qualify, the one
    closest to ending wins — that is the one with real urgency to advertise.

    Callers MUST treat None as "write a normal caption", never as "assume the
    usual discount".
    """
    candidates = await db.get_candidate_live_sales(product_key)
    if not candidates:
        return None

    live: list[FlashSale] = []
    for sale in candidates:
        result = evaluate_liveness(sale, now=now, max_staleness_seconds=max_staleness_seconds)
        if result.is_live:
            live.append(sale)
        else:
            logger.info(
                "flash_sale %s not advertisable: %s", sale.sale_id, result.reason,
            )

    if not live:
        return None

    live.sort(key=lambda s: _as_utc(s.ends_at) or datetime.max.replace(tzinfo=timezone.utc))
    return live[0]


def describe_discount(sale: FlashSale) -> str:
    """Human-readable discount for a caption, e.g. '25% off' / '$5 off'.

    Kept here so every surface renders the same sale identically — a caption and
    a reply must not describe the same discount differently.
    """
    if sale.discount_type == "percentage":
        value = int(sale.discount_value) if float(sale.discount_value).is_integer() else sale.discount_value
        return f"{value}% off"
    if sale.discount_type == "fixed_amount":
        symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(sale.currency, f"{sale.currency} ")
        return f"{symbol}{sale.discount_value:.2f} off"
    return "on sale"


def time_remaining(sale: FlashSale, now: datetime | None = None) -> timedelta | None:
    """Time until the sale ends, or None if unknown/ended."""
    now = _as_utc(now) or datetime.now(timezone.utc)
    ends_at = _as_utc(sale.ends_at)
    if ends_at is None or now >= ends_at:
        return None
    return ends_at - now

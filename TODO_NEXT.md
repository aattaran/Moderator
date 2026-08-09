# TODO_NEXT — single live work queue

> One queue per project. Do NOT create a second backlog-shaped file.
> Two agents are working this repo concurrently. **Check your lane before editing.**

## Active lanes (2026-08-08)

| Lane | Session | Owns | Status |
|---|---|---|---|
| **A — Posting** | `9f43717c` | TikTok posting reliability, session/proxy, `PLATFORMS` un-pause | IN FLIGHT |
| **B — Commerce** | `af4b86f0` | TikTok Shop flash-sale promotions (net-new files) | IN FLIGHT |

### Lane A owns — Lane B must NOT edit
- `core/tiktok_actions.py`
- `core/tiktok_selectors.py`
- `agents/tiktok_agent.py`
- `.env` → `PLATFORMS` (the TikTok un-pause)
- TikTok session / proxy / cookie state

Established: TikTok session is VALID through the residential proxy
(`200 :: Nature.Pulse`, file input found at t=10s). The earlier failure was a
fixed `sleep` racing proxy latency, not an expired cookie. **Do not "fix" this
by re-authing — that would undo Lane A's diagnosis.**

### Lane B owns — Lane A need not touch
- `core/tiktok_shop_client.py` (new — signed request layer)
- `core/tiktok_shop_promotions.py` (new — flash-sale activities)
- `storage/migrations/008_flash_sales.sql` (new)
- `config.py` → TikTok Shop credential block (additive only)
- `docs/arch-tiktok-shop.md` (new)

## Seam — ASSIGNED TO LANE A (operator decision, 2026-08-08)

Lane A owns wiring captions to live sale state, in
`strategies/elemnt_content_strategy.py` and `core/orchestrator.py::execute_tiktok_post`.
Lane B will not touch those files.

**The interface Lane A needs is built, tested, and ready now** — no need to wait
on the TikTok Shop API work:

```python
from core.flash_sale_state import get_live_sale, describe_discount, time_remaining

sale = await get_live_sale(db, product_key="elemnt_core")
if sale:
    # safe to mention the discount, e.g. describe_discount(sale) -> "25% off"
    await db.mark_flash_sale_advertised(sale.sale_id)
else:
    # write a NORMAL caption. Never assume "the usual discount".
    ...
```

Contract:
- `get_live_sale()` returns a sale **only** if it provably exists on TikTok Shop
  AND was confirmed still running within the last 15 min AND is inside its window.
- `None` means *write a normal caption*. It does not mean "no sale configured".
- Never hardcode a discount in caption text — a post outlives the sale.
- `describe_discount()` is the single renderer, so every surface words the same
  sale identically.

Until Lane B's API client exists, `get_live_sale()` simply always returns None
(no sale is ever confirmed), so wiring it now is safe and changes no behaviour.

## Queue

| # | What | Blocked on | Agent may proceed unasked? |
|---|---|---|---|
| 1 | ~~Verify TikTok Shop API contract~~ | — | DONE (blocked: login-gated, see `docs/arch-tiktok-shop.md`) |
| 2 | ~~Flash-sale state: migration 008 + model + DB layer + liveness predicate~~ | — | DONE — 29 tests, mutation-proven, e2e wiring verified |
| 3 | **TikTok Shop Partner Center login** — unblocks the whole contract | **OPERATOR** | no |
| 4 | Developer app → `app_key` / `app_secret` | **OPERATOR** | no |
| 5 | Seller authorization → `access_token` + `shop_cipher` | **OPERATOR** (needs #4) | no |
| 6 | Capture verified 202309 contract into `docs/arch-tiktok-shop.md` | needs #3 | YES once unblocked |
| 7 | Signed-request transport (HMAC + token refresh) | needs #6 | YES once #6 done |
| 8 | Promotion wrapper: create/schedule/end Flash Deal | needs #7 | YES once #7 done |
| 9 | Wire captions to live sale state | **Lane A** — interface is ready now | YES — Lane A may proceed |
| 10 | Un-pause TikTok (`PLATFORMS`) | Lane A owns | no — Lane A in flight |

## Delivered by Lane B this session

- `storage/migrations/008_flash_sales.sql` — flash sale state
- `storage/models.py` → `FlashSale` (additive)
- `storage/database.py` → flash-sale CRUD (additive, end of file)
- `core/flash_sale_state.py` — fail-closed liveness predicate + the seam interface
- `tests/test_flash_sale_state.py` — 31 tests; mutations injected and all caught
- `config.py` / `.env.example` — `TIKTOK_SHOP_*`, dry-run defaults **ON**
- `docs/arch-tiktok-shop.md` — verified vs unverified contract, dead ends

Full suite: 81 passed, no regressions.

### Adversarial review findings (self-review, honest state)

- **Bug found and fixed:** `now` was coerced with `.astimezone()`, which reads a
  naive datetime as host-local, while stored columns are read as UTC. On a
  non-UTC host this shifted the sale window and could keep an ENDED sale
  advertisable. Now every timestamp goes through `_as_utc`. Regression test
  added and verified to fail against the old code.
- **Not yet reachable in production (by design):** nothing calls
  `get_live_sale()` yet — that call site is the seam, and Lane A owns it. The
  commerce layer is built and tested but dead until Lane A wires it AND the API
  client exists. Do not read "81 tests pass" as "flash sales work".
- **Dead config (expected, temporary):** every `TIKTOK_SHOP_*` key is defined
  and consumed by nothing, because the client is blocked on Partner Center
  access. They activate with item #7.
- **Unused-but-intended API:** `describe_discount`, `time_remaining`,
  `get_flash_sales_by_status`, `mark_flash_sale_verified`,
  `mark_flash_sale_advertised` are unreferenced in prod — they are the surface
  for Lane A and for the future verification job.

## Money-path gate

Flash-sale creation writes real discounts against a live, selling shop.
Per global rules this is a money/pricing path: **nothing deploys or fires
against production without explicit operator approval**, regardless of gate colour.

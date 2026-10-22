# TikTok Shop Open API — research state

> Status: **contract NOT yet verified.** Do not write a client against this file's
> "unverified" rows. Research performed 2026-08-08 (Lane B, session `af4b86f0`).

## Why this file exists

To stop the next session from re-running the same dead ends. The three obvious
verification routes are all closed; see "Dead ends" below.

## Verified (multiple independent sources agree)

| Fact | Confidence |
|---|---|
| Current API version is `202309`; it is a breaking change from the 2021/22 API | high |
| Base host: `open-api.tiktokglobalshop.com` | high |
| Signing is HMAC-SHA256 keyed on `app_secret` | high |
| Request carries `app_key`, `timestamp`, `sign_method`, `sign` | high |
| Auth is `Authorization: Bearer <access_token>` (202309 moved it out of the query string) | high |
| `202309` addresses a shop by `shop_cipher`, replacing the legacy `shop_id` | high |
| Promotion API exposes: Create Activity, Search Activities, Get Activity, Update Activity, Deactivate Activity | high |
| A flash sale is the **Flash Deal** activity type; products render with a limited-time countdown | high |
| **Coupons cannot be created via the API** — search/get only. Only *activities* are creatable. | high |

## NOT verified — must not be guessed

| Unknown | Why it matters |
|---|---|
| Exact path + version segment for create-activity (e.g. `/promotion/202309/activities`) | wrong path = 404 at runtime, discovered only in prod |
| Exact request body schema for a Flash Deal (product/SKU discount shape, absolute vs percentage) | **money path** — a wrong field could set the wrong price on a live, selling shop |
| The precise sign-string construction (param sort order, path inclusion, body handling, `app_secret` bracketing) | a wrong signature fails 100% of calls; the exact rule is login-gated |
| Rate limits and activity-count caps | unknown throttling behaviour |
| Whether an activity can be ended early vs only deactivated | needed for "end the flash sale" |

## Dead ends (do not retry)

1. **`partner.tiktokshop.com/docv2/*`** — every page returns a 365-byte shell with
   "Log in / Join now". The whole reference is behind a Partner Center account.
   Tried: WebFetch and Firecrawl, on the promotion overview, the promotion API
   reference, and the signing page. All identical.
2. **Official public Postman workspace** (`tiktok-shop-open`, collection
   `18272735-253d12bf-f3f8-4e4d-9bf1-0ff93c13fa5f`). Fetchable without auth via
   `https://www.postman.com/_api/collection/<id>?populate=true`, **but it is the
   2022 legacy API**: `updatedAt` 2022-02-23, paths like `/api/products`, uses
   `shop_id`, token in the query string, and **zero promotion endpoints**.
   Useless for 202309.
3. `github.com/Lundehund/tiktok-shop-api` — 404, repo is gone.

## The one route that works

A Partner Center login. Every unknown above is documented there. Access comes
from registering the developer app (which is required for the build anyway), so
this is not extra work — it is step 1 of the real path.

## Sequence once access exists

1. Register developer app in Partner Center → `app_key`, `app_secret`
2. Authorize the ELEMNT seller account → `access_token`, `refresh_token`, `shop_cipher`
3. Capture the verified contract into this file (replace the "NOT verified" table)
4. Build transport layer (sign + token refresh) against the verified sign rule
5. Build the Promotion wrapper; **exercise against sandbox before any live shop**
6. Only then wire captions to live sale state

## Money-path gate

Flash-sale creation writes real discounts on a live, selling shop. Nothing runs
against production without explicit operator approval, regardless of test status.
A dry-run/sandbox mode is mandatory before the first live call.

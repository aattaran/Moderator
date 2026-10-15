## Never Guess. Never Assume.

Read source / run diagnostics / inspect runtime data before acting. Speculation that looks like fact is the leading source of regressions. Surface uncertainty explicitly: "I am not sure if X — let me check" beats committing a wrong-shaped change. When in doubt: read, log, test, ask.

---

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **README.md is stale** — it describes the X-only original (single platform, 1vCPU/2GB droplet). The code is multi-platform (X/FB/IG/TikTok/YouTube/Reddit) on a 2vCPU/4GB droplet. Trust this CLAUDE.md, not README.md.

## Project Overview

Moderator is an autonomous multi-platform social media agent that posts, engages, and grows accounts 24/7. Uses Playwright browser automation for X/Facebook/TikTok, `instagrapi` mobile API for Instagram, and Gemini 2.5 Flash for all content generation.

**Two personas, one engine:**
- **X** = Ali Attaran (@AlyAttaran) — build-in-public, AI/tech, project updates
- **Facebook + Instagram + TikTok + YouTube** = ELEMNT™ by Shifana® (supplement brand) — health tips, product spotlights, science explainers

**Platform accounts:**
- X: @AlyAttaran
- Instagram: @elemnt_shifana (login as aliattaran, switch to elemnt_shifana)
- TikTok: @nature.pulse_ — **paused**
- YouTube: Elemnt-Shifana (@Elemnt-1)
- Facebook: ELEMNT Group (ELEMNT page identity)
- Reddit: Super_External_60 — **code ready, waiting for API approval**

## Commands

```bash
# Run locally
python main.py run                      # Continuous scheduled mode (no startup posts)
python main.py run --startup-test       # Same but posts once per platform on startup
python main.py post                     # Single X tweet
python main.py engage                   # X engagement cycle
python main.py reflect                  # X content reflection
python main.py elemnt-reflect           # ELEMNT content reflection (FB/IG)
python main.py scrape [username]        # Scrape engagement metrics (own posts)
python main.py evaluate                 # Recompute weights from existing engagement data
python main.py analytics                # Engagement analytics summary
python main.py status                   # Show status + weights
python main.py add-target <username> --followers N --engagement 0.05 --relevance 0.5
python main.py campaign launch <id>     # Launch freebie campaign (skills/fleet/ppc/video/setup)
python main.py campaign monitor         # Check replies + auto-DM download links
python main.py campaign status          # Per-campaign reply/follow/DM stats
python main.py campaign-focus mcro_launch  # Switch active content-focus campaign (separate from `campaign` group)
python main.py campaign-focus none      # Clear campaign focus
python main.py campaign-list            # List all content-focus campaigns
python main.py reddit-post              # Post to Reddit subreddit
python main.py reddit-engage            # Reddit comment cycle
python main.py reddit-karma             # Show Reddit karma
python main.py ugc-video                # Generate UGC video (uses .env config)
python main.py ugc-video --actor strategies/references/actors/2/ --topic blood_sugar --clips 3 --duration 8
python main.py ugc-video --style casual_review --concept lifestyle --hook product_action --dry-run
python main.py ugc-video --kling-model kling-v2-master --kling-mode std --cfg-scale 0.8 --aspect 1:1
python main.py ui                       # Launch UGC web UI on 127.0.0.1:8765

# Tests
pytest tests/                           # All tests
pytest tests/test_image_generator.py    # Single test file
pytest tests/ -k "test_name"            # Single test by name
# Existing coverage: database, weight_manager, x_agent, computer_use,
# image_generator, video_generator. No orchestrator or scheduler tests.

# Docker (production)
docker compose build && docker compose up -d
docker compose logs --tail 30

# Deploy to droplet
tar -czf /tmp/mod.tar.gz --exclude='.git' --exclude='__pycache__' --exclude='data/product_videos' --exclude='data/product_images' --exclude='browser-profile' .
scp -i ~/.ssh/id_moderator /tmp/mod.tar.gz root@137.184.137.154:/tmp/moderator.tar.gz
ssh -i ~/.ssh/id_moderator root@137.184.137.154 "cd /opt/moderator && docker compose down && tar xzf /tmp/moderator.tar.gz && chmod -R 777 data && docker compose build && docker compose up -d"

# Media sync
python scripts/upload_to_spaces.py      # Upload new videos to DO Spaces
python scripts/export_session.py        # X.com cookies via Chrome CDP (laptop only)
```

## Architecture — Three Layers

The system has three distinct layers that work together:

### Layer 1: Agents (`agents/`)
Each platform has an agent that extends `BaseAgent` (ABC). The base class defines four abstract methods:
- `post_content(content, style, topic) -> Post`
- `engage(target_username, comment_text, style, topic) -> Comment`
- `scrape_own_metrics(own_username) -> list[dict]`
- `get_platform_name() -> str`

The base class also provides `check_rate_limit(action)` and `request_approval(content, action)`.

**Rate limits** live on `Settings` (`config.py`): `POSTS_PER_DAY` (default), `FACEBOOK_POSTS_PER_DAY`, `TIKTOK_POSTS_PER_DAY`, `MAX_COMMENTS_PER_HOUR`. `check_rate_limit` queries `db.count_posts_today(platform)` / `count_comments_last_hour(platform)` and raises `RateLimitError` when exceeded. Per-platform overrides are resolved in `_get_daily_post_limit`.

**Approval flow (HITL):** Gated by `REQUIRE_APPROVAL` env flag. When enabled, `request_approval` prints the action + content and blocks on `input("Approve? (y/n):")` via `run_in_executor`. Raises `ApprovalDenied` on `n` or on `EOFError` (no TTY — so enabling approval in Docker without an interactive session will reject every action). Default is off in production.

**Agent lifecycle:** Non-Playwright agents (Instagram, YouTube, Reddit) pass `browser=None` to `super().__init__()` and implement their own `start()`/`stop()` methods. The orchestrator calls `start()` during `initialize()` — each wrapped in try/except so one platform's failure doesn't kill the rest. Failed platforms are removed from `self.agents`.

### Layer 2: Actions (`core/*_actions.py`)
Platform-specific browser/API operations. Each agent delegates to its actions class:
- `XActions` / `FacebookActions` / `TikTokActions` — Playwright page interactions
- `InstagrapiActions` — `instagrapi` mobile API client
- `YouTubeActions` — YouTube Data API v3 (OAuth2)
- `RedditActions` — PRAW wrapper

### Layer 3: Selectors (`core/*_selectors.py`)
CSS/XPath selectors for Playwright-based platforms (X, Facebook, TikTok). Kept separate from actions so selector changes don't touch business logic.

### Orchestrator (`core/orchestrator.py`)
Top-level coordinator. Wires agents, strategies, and the scheduler together. Key pattern: the orchestrator owns `execute_*` methods (e.g., `execute_smart_post`, `execute_facebook_post`) which the scheduler calls as callbacks.

### Scheduler (`core/scheduler.py`)
APScheduler-based. Post times are randomized within waking hours (8-23) at startup. The scheduler doesn't know about content types — it calls `smart_post_callback` which delegates to `weight_manager.select("post_type")` at runtime.

**Wiring pattern:** `main.py` → creates `Orchestrator` → creates `TaskScheduler` → `scheduler.set_callbacks(smart_post_callback=orchestrator.execute_smart_post, ...)` → `scheduler.setup()` adds APScheduler jobs that call `_safe_run("callback_name")`.

## Content Generation

### Gemini SDK Pattern
All content generation uses `google-genai` SDK (NOT Anthropic). The pattern throughout:
```python
from google import genai
client = genai.Client(api_key=settings.GEMINI_API_KEY)
response = client.models.generate_content(
    model="gemini-2.5-flash-preview-05-20",
    contents=prompt_string,
)
return response.text
```
Each strategy module has its own `_get_gemini_client()` helper. No shared Gemini singleton.

### Two Content Engines
- `strategies/content_strategy.py` — X persona (Ali Attaran). Uses `PERSONA` + `STYLE_PROMPTS` + `TOPIC_DESCRIPTIONS`. Enriched with real project facts (MCRO metrics, Jarvis details, etc.).
- `strategies/elemnt_content_strategy.py` — ELEMNT brand. Uses `ELEMNT_PERSONA` + `ELEMNT_STYLE_PROMPTS` + `ELEMNT_TOPICS`. Per-platform hashtag rules and character limits.
- `strategies/reddit_content_strategy.py` — Reddit persona with subreddit-specific configs and 10:1 non-promotional to promotional ratio.

Each strategy takes a `WeightManager` and uses weighted random selection to pick style + topic.

### Adaptive Learning Loop
1. **WeightManager** — Weighted random selection for styles, topics, post types. Starts at 1.0 with overrides (threads 3x, MCRO 2.5x). Adjusts based on engagement. Floor at 0.05.
2. **ContentReflector** — Every 3 days, sends top/bottom posts to Gemini for analysis. Produces `StyleGuideline` records (per-platform) with patterns, anti-patterns, and actionable rules.
3. **FeedbackLoop** — Connects `MetricsScraper` → `WeightManager`. Scrapes engagement, computes scores, adjusts weights.

## Database

SQLite with WAL mode at `data/moderator.db` via `aiosqlite`. Single async connection (`Database._get_conn()`).

**Migrations:** Numbered SQL files in `storage/migrations/` (001_initial.sql through 007_ugc_run_params.sql). Auto-applied on startup — `001_initial.sql` runs first, then all others sorted by filename. Failed migrations are skipped with a warning (idempotent — uses `IF NOT EXISTS`). To add a migration: create `storage/migrations/008_your_feature.sql`.

**Key tables:** `posts`, `comments`, `target_accounts`, `weight_entries`, `style_guidelines` (per-platform via `platform` column), `campaigns`, `campaign_fulfillments`, `reddit_karma_log`, `ugc_video_jobs` (with `run_params_json` for UI re-run).

## Configuration

All config via `.env`, loaded through pydantic-settings (`config.py` → `Settings`). Singleton via `get_settings()` with `@lru_cache`. Only `GEMINI_API_KEY` is required — everything else has defaults.

**Critical:** `docker compose restart` does NOT re-read `.env` — must `docker compose down && docker compose up -d`.

Active platforms controlled by `PLATFORMS` env var: comma-separated string like `"x,instagram,youtube,facebook"`.

## Key Design Decisions

- **Instagram uses `instagrapi` (mobile API)**, NOT Playwright. Datacenter IPs are blocked for IG web, but mobile API works with IPRoyal residential proxy. Login from laptop, save session, upload to droplet.
- **X/Facebook/TikTok use Playwright** with `storage_state` for cookie-based auth. X and Facebook work from datacenter IPs (no proxy needed).
- **Resilient platform init** — each platform's `start()` is wrapped in try/except. If one fails, it's removed from `self.agents` and the rest keep running.
- **Political content filter** — ~60 keywords checked against post text, bios, and usernames before engaging. All platforms.
- **Reddit karma phases** — comment-only (0-50 karma) → post+comment (50-200) → full with soft promotion (200+). 10:1 ratio enforced.

## Auth Flow Per Platform

- **X:** Chrome CDP → `data/auth_state.json` (Playwright storage_state). Use `scripts/export_session.py` on laptop.
- **Facebook:** VNC login on droplet (port 5900) → save cookies via `storage_state()`. Must switch to ELEMNT page first.
- **Instagram:** `instagrapi` login from laptop → `data/instagram_session_settings.json` → upload to droplet. IPRoyal proxy required.
- **TikTok:** Chrome CDP cookie extraction → `data/tiktok_auth_state.json`. httpOnly cookies via `Network.getAllCookies`.
- **YouTube:** OAuth2 via `scripts/youtube_auth.py` → `data/youtube_credentials.json`. Token auto-refreshes.
  - **Account:** `data/youtube_credentials.json` authorizes the **tiktokshopnature@gmail.com** channel (Elemnt-Shifana / @Elemnt-1). The sibling `auth_youtube_commentssong.py` → `data/youtube_credentials_commentssong.json` is a *separate* channel. Scope is `youtube.upload` only (no comment/analytics/channel-read).
  - **OAuth app:** GCP project `moderator-491715`, **"Testing"** publishing status. Only allow-listed Google accounts can authorize — any other email is rejected with `403 access_denied`. To authorize a new account, add it as a **Test user** at Console → Google Auth Platform → Audience (no API for this; manual, requires owner of `moderator-491715`).
  - **Re-auth gotcha:** the login auto-uses whichever Google account is signed into the browser. Use `prompt="select_account consent"` and verify the account (via `oauth2/v3/userinfo`) before saving, or you'll silently overwrite the file with the wrong channel's token. A dead token shows as `invalid_grant` on refresh → re-run the auth.

## Campaign System

Content focus driven by `data/campaigns.json` — no redeploy needed. Set `"active_campaign"` in the JSON → 70% of X posts use campaign topics. Each campaign defines: `focus_features`, `links`, `talking_points`, `thread_topics`, `cta`, `tone`.

**CLI:** `python main.py campaign-focus mcro_launch` / `campaign-list` / `campaign-focus none`

## UGC Video Pipeline

**SaaS direction:** The pipeline is product and brand agnostic. All system prompts in `media/creative_angles.py`, `media/ugc_image_generator.py`, and `media/ugc_video_generator.py` use generic "product" language. The named product entries (dbh/ark/nmnh/h2) are your own product catalog — any new product uses the "custom" path (free-text description + images). Originals backed up as `.bak` files.

`media/ugc_video_generator.py` — 6-stage pipeline (proven from video-ad project, 130+ validated runs):
1. Script gen (Gemini `gemini-2.5-flash`) — 5 styles × 5 concepts × 4 hooks, overridable via `--style`/`--concept`/`--hook` or UI dropdowns
2. Frame gen (Gemini `gemini-2.5-flash-image`) — actor + product + scene photos → single start frame, reused for all clips. Grid-sheets included for Gemini, excluded from Kling.
3. Video gen (Kling direct API `kling-v3` Pro) — image-to-video per clip. No multi-image refs to Kling — character consistency comes from the Gemini start frame. Params: `model_name`, `mode` (std/pro → 720p/1080p), `cfg_scale`, `sound`, `aspect_ratio`.
4. Audio extract (FFmpeg → MP3, `libmp3lame -q:a 2`)
5. Lip sync (Sync Lipsync 2.0 Pro via fal.ai `fal-ai/sync-lipsync/v2`) — re-warps mouth to native Kling audio
6. Stitch (FFmpeg hard cuts)

**`--dry-run`** stops after Stage 2 (zero Kling spend). **Preview-gate** (UI default) pauses after Stage 2 for manual confirm/abort.

Actor photos in `strategies/references/actors/N/`. Product photos in `data/product_images/{product_key}/` (custom: `data/product_images/custom/`). Scene refs in `strategies/references/scenes/`. Output: `data/media/ugc_videos/YYYY-MM-DD/{product}_{platform}_{style}_{concept}_{hook}_{clips}x{duration}s_{resolution}_{timestamp}/`.

**DB tracking:** Every run (CLI and UI) inserts/updates a row in `ugc_video_jobs` with per-stage status columns (`frame_status`, `video_status`, `lipsync_status`, `assembly_status`) and `run_params_json` for UI re-run.

## UGC Web UI

FastAPI + HTMX single-page app at `127.0.0.1:8765` (localhost only, no auth). Launch: `python main.py ui`.

**Stack:** FastAPI, uvicorn, sse-starlette, Jinja2. Files in `ui/` — `server.py` (endpoints + SSE bus + asyncio lock), `assets.py` (path-guarded actor/scene enumeration), `schemas.py` (pydantic `RunRequest` with `Literal` enums), `costs.py` (per-unit price constants), `templates/index.html`, `static/{app.css,app.js}`.

**Form fields:** Product (→ cascading Topic; "Custom" option accepts free-text description + images from `data/product_images/custom/`), Platform, Actor (thumbnail grid, required), Scene (image OR description OR none), Clips (1-12 number input), Duration (1-30s number input), Aspect (9:16/16:9/1:1), Resolution (720p/1080p), Style/Concept/Visual Hook (dropdowns with Random default), Dry-run checkbox, Preview-gate checkbox (default on). Advanced: Kling model, cfg_scale slider (default 0.7), sound, TTS voice, pose, bottle-closeup, multi-shot hint, extend-clips.

**Key behaviors:**
- **Concurrency lock** — one run at a time, second submit returns HTTP 409
- **SSE log tail** — real-time generator log stream via `/api/runs/{id}/events`
- **Preview-gate** — after Gemini Stages 1-2, pipeline pauses with `status=awaiting_confirmation`. SSE emits `preview_ready` with frame URL + cost estimate. User clicks Confirm (→ Kling stages) or Abort (→ `status=aborted`, zero Kling spend). Endpoints: `POST /api/runs/{id}/confirm`, `POST /api/runs/{id}/abort`.
- **History panel** — filterable table (product/status/date) from `ugc_video_jobs`. Re-run pre-fills form from `run_params_json`. Delete removes DB row + run dir (path-guarded). Play opens inline video modal.
- **Cost estimate** — reactive footer, updates on form change. `ui/costs.py` has per-unit constants.
- **localStorage** — last-submitted values auto-fill on reload (actor/scene excluded for safety)

**Security:** Bind `127.0.0.1` only (never `0.0.0.0`). No CORSMiddleware. No docker-compose port mapping. Asset IDs validated via regex + `Path.resolve()` + `is_relative_to()` (symlink-safe). `scene_description` free-text field: 500-char cap, control-char/injection-token filter. `tts_voice` sanitized to `[A-Za-z0-9._ -]`. SQL filters use `?` placeholders with whitelisted column values. Pillow `MAX_IMAGE_PIXELS=50M` for thumbnail DoS protection.

## Deployment

DigitalOcean droplet (2 vCPU, 4GB RAM, nyc1). Docker container with mounted `data/` and `browser-profile/` volumes. VNC on port 5900. Media in DO Spaces bucket `moderator-media`.

**Media sync cadence:** APScheduler `IntervalTrigger(hours=2)` job id `media_sync` in `core/scheduler.py` — calls the `media_sync_callback` wired by `main.py` (which uses `scripts/upload_to_spaces.py`). Not a cron, not external — runs in-process alongside the post/engage jobs, so it stops when the container stops.

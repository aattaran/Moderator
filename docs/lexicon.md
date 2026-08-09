# Param & Data-Flow Lexicon

> Auto-generated 2026-05-05 23:47 by `~/.claude/scripts/gen-lexicon.js`.
> **Rule:** Before defining any parameter, env var, config key, or data field — check this file.
> If it exists, use the exact name. Never introduce a synonym.

## Env Vars

> Before adding a new env var, check this list. Use the exact existing name.

| Var | Used in |
|-----|---------|
| `COMMENTS_SONG_BASE_URL` | scripts/verify_step1_comments_song.py |
| `DO_SPACES_KEY` | scripts/sync_media.py, scripts/upload_to_spaces.py |
| `DO_SPACES_SECRET` | scripts/sync_media.py, scripts/upload_to_spaces.py |
| `FAL_API_KEY` | strategies/references/test-bottle-label-models.js |
| `FAL_KEY` | strategies/references/test-bottle-label-models.js, tests/test_video_generator.py |
| `X_PASSWORD` | scripts/docker_login.py |
| `X_USERNAME` | scripts/docker_login.py |

## Config File Keys

### `.env.example`
```
GEMINI_API_KEY
KIE_API_KEY
FAL_API_KEY
X_USERNAME
X_PASSWORD
PLATFORM
BROWSER_PROFILE_PATH
POSTS_PER_DAY
ENGAGEMENT_CYCLE_INTERVAL_HOURS
COMMENTS_PER_CYCLE
ANALYTICS_SCRAPE_INTERVAL_HOURS
REFLECTION_MIN_POSTS
REFLECTION_POST_AGE_HOURS
CAMPAIGN_CHECK_INTERVAL_MINUTES
MAX_DMS_PER_HOUR
WEIGHT_EVAL_PERIOD_DAYS
LEARNING_RATE
MIN_WEIGHT_FLOOR
MAX_POSTS_PER_DAY
MAX_COMMENTS_PER_HOUR
REQUIRE_APPROVAL
DRY_RUN
ENABLE_VNC
DB_PATH
```

## Frequently Duplicated Params

> Grep for these before naming something new — if a name exists, use it exactly.

| Param | Occurrences |
|-------|-------------|
| `prompt` | 269 |
| `task` | 34 |
| `channel` | 25 |
| `token` | 12 |
| `port` | 4 |
| `outputDir` | 3 |
| `apiKey` | 2 |

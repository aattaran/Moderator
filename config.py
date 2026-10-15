"""Global configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # API Keys
    GEMINI_API_KEY: str = ""
    KIE_API_KEY: str = ""
    FAL_API_KEY: str = ""
    ATLASCLOUD_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""  # Optional — only if using Claude API

    # Platform
    PLATFORM: str = "x"
    PLATFORMS: str = "x"  # comma-separated: "x", "x,facebook", "x,facebook,instagram"
    BROWSER_PROFILE_PATH: str = "./browser-profile"
    FACEBOOK_GROUP_ID: str = ""
    FACEBOOK_POSTS_PER_DAY: int = 3
    TIKTOK_POSTS_PER_DAY: int = 2

    # Scheduling
    POSTS_PER_DAY: int = 3
    ENGAGEMENT_CYCLE_INTERVAL_HOURS: int = 2
    COMMENTS_PER_CYCLE: int = 5
    ANALYTICS_SCRAPE_INTERVAL_HOURS: int = 6

    # Adaptive learning
    WEIGHT_EVAL_PERIOD_DAYS: int = 14
    LEARNING_RATE: float = 0.1
    MIN_WEIGHT_FLOOR: float = 0.05

    # Content reflection
    REFLECTION_MIN_POSTS: int = 15
    REFLECTION_POST_AGE_HOURS: int = 48

    # Campaigns
    CAMPAIGN_CHECK_INTERVAL_MINUTES: int = 30
    MAX_DMS_PER_HOUR: int = 10

    # Rate limits
    MAX_POSTS_PER_DAY: int = 15
    MAX_COMMENTS_PER_HOUR: int = 15

    # Safety
    REQUIRE_APPROVAL: bool = False
    DRY_RUN: bool = False

    # Browser
    ENABLE_VNC: bool = False

    # Proxy (residential proxy for Instagram/TikTok)
    PROXY_SERVER: str = ""
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    # X credentials
    X_USERNAME: str = ""
    X_PASSWORD: str = ""

    # Instagram credentials (for login via proxy)
    IG_USERNAME: str = ""
    IG_PASSWORD: str = ""
    IG_SWITCH_TO: str = ""  # Switch to linked account after login

    # Reddit credentials (PRAW)
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USERNAME: str = ""
    REDDIT_PASSWORD: str = ""
    REDDIT_USER_AGENT: str = ""
    REDDIT_COMMENTS_PER_DAY: int = 10
    REDDIT_POSTS_PER_DAY: int = 2

    # TikTok Shop Open API (flash sale / Flash Deal promotions)
    # From Partner Center: developer app gives key+secret, seller authorization
    # gives the tokens and shop_cipher. See docs/arch-tiktok-shop.md.
    TIKTOK_SHOP_APP_KEY: str = ""
    TIKTOK_SHOP_APP_SECRET: str = ""
    TIKTOK_SHOP_ACCESS_TOKEN: str = ""
    TIKTOK_SHOP_REFRESH_TOKEN: str = ""
    TIKTOK_SHOP_CIPHER: str = ""      # 202309 addresses a shop by cipher, not shop_id
    TIKTOK_SHOP_BASE_URL: str = "https://open-api.tiktokglobalshop.com"
    # Writing a discount is a money path. Default ON so an unconfigured or
    # half-configured deploy cannot mutate prices on a live, selling shop —
    # this must be turned off deliberately, per operator approval.
    TIKTOK_SHOP_DRY_RUN: bool = True

    # Kling AI (direct API for UGC video generation)
    KLING_ACCESS_KEY_ID: str = ""
    KLING_SECRET_KEY: str = ""

    # UGC Video Pipeline
    UGC_ACTOR_DIR: str = ""           # Path to actor reference photos (e.g. data/actors/1/)
    UGC_CLIP_COUNT: int = 3           # Clips per video (3-6)
    UGC_CLIP_DURATION: int = 8        # Seconds per clip (5, 8, or 10)
    UGC_SCENE_IMAGE: str = ""         # Optional scene reference image path
    UGC_ACTOR_GENDER: str = "female"  # "male" or "female" — for TTS voice matching

    # Database
    DB_PATH: str = "data/moderator.db"

    @model_validator(mode="after")
    def check_api_key(self):
        if not self.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in .env or as an environment variable."
            )
        return self


from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance (singleton)."""
    return Settings()

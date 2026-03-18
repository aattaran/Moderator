"""Global configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API
    ANTHROPIC_API_KEY: str = ""
    MODEL: str = "claude-opus-4-6"

    # Platform
    PLATFORM: str = "x"
    BROWSER_PROFILE_PATH: str = "./browser-profile"

    # Scheduling
    POSTS_PER_DAY: int = 3
    ENGAGEMENT_CYCLE_INTERVAL_HOURS: int = 2
    COMMENTS_PER_CYCLE: int = 5
    ANALYTICS_SCRAPE_INTERVAL_HOURS: int = 6

    # Adaptive learning
    WEIGHT_EVAL_PERIOD_DAYS: int = 14
    LEARNING_RATE: float = 0.1
    MIN_WEIGHT_FLOOR: float = 0.05

    # Rate limits
    MAX_POSTS_PER_DAY: int = 10
    MAX_COMMENTS_PER_HOUR: int = 10

    # Safety
    REQUIRE_APPROVAL: bool = False
    DRY_RUN: bool = False

    # Display
    DISPLAY_WIDTH: int = 1024
    DISPLAY_HEIGHT: int = 768
    ENABLE_VNC: bool = False

    # Database
    DB_PATH: str = "data/moderator.db"

    @model_validator(mode="after")
    def check_api_key(self):
        if not self.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it in .env or as an environment variable."
            )
        return self


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

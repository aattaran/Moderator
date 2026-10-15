"""Seed target accounts for engagement."""
import asyncio
import sys
sys.path.insert(0, "/app")

from config import Settings
from storage.database import Database
from strategies.targeting_strategy import TargetingStrategy


# Target accounts — high-engagement tech/AI/startup accounts
TARGETS = [
    # Tech thought leaders
    ("elonmusk", 180000000, 0.02, 0.6),
    ("sama", 3000000, 0.04, 0.9),         # Sam Altman
    ("ylecun", 800000, 0.03, 0.8),         # Yann LeCun
    ("kaborosays", 500000, 0.05, 0.85),    # Andrej Karpathy
    ("demaborosenior", 200000, 0.06, 0.8),
    # AI/ML community
    ("emaboringai", 300000, 0.04, 0.9),
    ("ai_explained", 200000, 0.05, 0.85),
    ("bindureddy", 150000, 0.04, 0.7),
    # Tech startups
    ("paulg", 1500000, 0.03, 0.8),         # Paul Graham
    ("naval", 2000000, 0.02, 0.7),
    ("garrytan", 500000, 0.04, 0.75),
    ("pmarca", 1500000, 0.03, 0.7),        # Marc Andreessen
    # Developer community
    ("levelsio", 500000, 0.05, 0.8),
    ("t3dotgg", 300000, 0.05, 0.75),
    ("fireship_dev", 400000, 0.04, 0.7),
    # AI companies
    ("AnthropicAI", 500000, 0.03, 0.9),
    ("OpenAI", 5000000, 0.02, 0.85),
    ("GoogleDeepMind", 1000000, 0.02, 0.8),
    ("xaborai", 2000000, 0.02, 0.7),
    ("huggingface", 500000, 0.04, 0.85),
]


async def main():
    config = Settings()
    db = Database(config.DB_PATH)
    await db.initialize()
    targeting = TargetingStrategy(db)

    for username, followers, engagement, relevance in TARGETS:
        target_id = await targeting.add_target(
            platform="x",
            username=username,
            follower_count=followers,
            engagement_rate=engagement,
            relevance_score=relevance,
        )
        print(f"Added @{username} (id={target_id})")

    print(f"\nSeeded {len(TARGETS)} target accounts.")


if __name__ == "__main__":
    asyncio.run(main())

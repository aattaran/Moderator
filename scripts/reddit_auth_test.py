"""Verify Reddit PRAW credentials. Run on laptop before deploying.

Usage: python scripts/reddit_auth_test.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings


def main():
    import praw

    config = Settings()
    if not config.REDDIT_CLIENT_ID:
        print("ERROR: REDDIT_CLIENT_ID not set in .env")
        print("Go to https://www.reddit.com/prefs/apps → create app (type: script)")
        return

    reddit = praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        username=config.REDDIT_USERNAME,
        password=config.REDDIT_PASSWORD,
        user_agent=config.REDDIT_USER_AGENT or f"Moderator:v1.0 (by /u/{config.REDDIT_USERNAME})",
    )

    user = reddit.user.me()
    print(f"Logged in as: /u/{user.name}")
    print(f"Comment karma: {user.comment_karma}")
    print(f"Link karma: {user.link_karma}")
    print(f"Total karma: {user.comment_karma + user.link_karma}")
    print(f"Account age: {user.created_utc}")
    print("\nCredentials verified — ready to deploy.")


if __name__ == "__main__":
    main()

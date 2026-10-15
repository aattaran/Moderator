"""Reddit actions using PRAW (Python Reddit API Wrapper)."""

import logging
import time

import praw
from praw.exceptions import RedditAPIException

logger = logging.getLogger(__name__)


class RedditActions:
    """Wraps PRAW for Reddit API operations. All methods are synchronous —
    the agent wraps them in asyncio.to_thread()."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        user_agent: str = "",
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._user_agent = user_agent or f"Moderator:v1.0 (by /u/{username})"
        self.reddit: praw.Reddit | None = None

    def login(self) -> bool:
        """Authenticate with Reddit via PRAW."""
        try:
            self.reddit = praw.Reddit(
                client_id=self._client_id,
                client_secret=self._client_secret,
                username=self._username,
                password=self._password,
                user_agent=self._user_agent,
            )
            user = self.reddit.user.me()
            logger.info("Reddit: logged in as /u/%s (karma: %d)", user.name, user.comment_karma + user.link_karma)
            return True
        except Exception as e:
            logger.error("Reddit: login failed: %s", e)
            return False

    def is_authenticated(self) -> bool:
        """Check if PRAW client is authenticated."""
        try:
            return self.reddit is not None and self.reddit.user.me() is not None
        except Exception:
            return False

    def _require_auth(self):
        """Raise if not authenticated."""
        if not self.reddit:
            raise RuntimeError("Reddit: not authenticated — call login() first")

    def get_karma(self) -> dict:
        """Get current karma breakdown."""
        self._require_auth()
        user = self.reddit.user.me()
        return {
            "username": user.name,
            "comment_karma": user.comment_karma,
            "link_karma": user.link_karma,
            "total_karma": user.comment_karma + user.link_karma,
        }

    def get_hot_posts(self, subreddit: str, limit: int = 25) -> list[dict]:
        """Get hot posts from a subreddit."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            posts = []
            for submission in sub.hot(limit=limit):
                posts.append(self._submission_to_dict(submission))
            return posts
        except Exception as e:
            logger.error("Reddit: failed to get hot posts from r/%s: %s", subreddit, e)
            return []

    def get_new_posts(self, subreddit: str, limit: int = 15) -> list[dict]:
        """Get new posts from a subreddit."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            posts = []
            for submission in sub.new(limit=limit):
                posts.append(self._submission_to_dict(submission))
            return posts
        except Exception as e:
            logger.error("Reddit: failed to get new posts from r/%s: %s", subreddit, e)
            return []

    def search_subreddit(self, subreddit: str, query: str, limit: int = 10) -> list[dict]:
        """Search a subreddit for posts matching a query."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            posts = []
            for submission in sub.search(query, sort="new", time_filter="week", limit=limit):
                posts.append(self._submission_to_dict(submission))
            return posts
        except Exception as e:
            logger.error("Reddit: search failed in r/%s: %s", subreddit, e)
            return []

    def submit_text_post(self, subreddit: str, title: str, body: str) -> dict | None:
        """Submit a text post to a subreddit."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            submission = sub.submit(title=title, selftext=body)
            logger.info("Reddit: posted to r/%s — %s", subreddit, submission.shortlink)
            return {
                "id": submission.id,
                "url": submission.shortlink,
                "subreddit": subreddit,
                "title": title,
            }
        except RedditAPIException as e:
            for item in e.items:
                if item.error_type == "RATELIMIT":
                    logger.warning("Reddit: rate limited — %s", item.message)
                else:
                    logger.error("Reddit: API error posting to r/%s: %s", subreddit, item.message)
            return None
        except Exception as e:
            logger.error("Reddit: failed to post to r/%s: %s", subreddit, e)
            return None

    def submit_link_post(self, subreddit: str, title: str, url: str) -> dict | None:
        """Submit a link post to a subreddit."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            submission = sub.submit(title=title, url=url)
            logger.info("Reddit: link posted to r/%s — %s", subreddit, submission.shortlink)
            return {
                "id": submission.id,
                "url": submission.shortlink,
                "subreddit": subreddit,
                "title": title,
            }
        except RedditAPIException as e:
            for item in e.items:
                logger.error("Reddit: API error: %s", item.message)
            return None
        except Exception as e:
            logger.error("Reddit: failed to link-post to r/%s: %s", subreddit, e)
            return None

    def comment_on_submission(self, submission_id: str, body: str) -> dict | None:
        """Comment on a submission by ID."""
        try:
            self._require_auth()
            submission = self.reddit.submission(id=submission_id)
            comment = submission.reply(body)
            logger.info("Reddit: commented on %s in r/%s", submission_id, submission.subreddit.display_name)
            return {
                "comment_id": comment.id,
                "submission_id": submission_id,
                "subreddit": submission.subreddit.display_name,
            }
        except RedditAPIException as e:
            for item in e.items:
                if item.error_type == "RATELIMIT":
                    logger.warning("Reddit: comment rate limited — %s", item.message)
                else:
                    logger.error("Reddit: comment API error: %s", item.message)
            return None
        except Exception as e:
            logger.error("Reddit: failed to comment on %s: %s", submission_id, e)
            return None

    def get_subreddit_rules(self, subreddit: str) -> list[str]:
        """Get subreddit rules as a list of strings."""
        try:
            self._require_auth()
            sub = self.reddit.subreddit(subreddit)
            return [rule.short_name for rule in sub.rules]
        except Exception as e:
            logger.debug("Reddit: could not fetch rules for r/%s: %s", subreddit, e)
            return []

    @staticmethod
    def _submission_to_dict(submission) -> dict:
        return {
            "id": submission.id,
            "title": submission.title,
            "body": (submission.selftext or "")[:500],
            "score": submission.score,
            "num_comments": submission.num_comments,
            "url": submission.shortlink,
            "subreddit": submission.subreddit.display_name,
            "author": str(submission.author) if submission.author else "[deleted]",
            "created_utc": submission.created_utc,
            "is_self": submission.is_self,
        }

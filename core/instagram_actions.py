"""Instagram actions using instagrapi (mobile API at i.instagram.com).

Works from datacenter IPs — no browser automation or residential proxy needed.
"""

import json
import logging
import os
from pathlib import Path
from urllib.parse import unquote

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    FeedbackRequired,
    PleaseWaitFewMinutes,
)

logger = logging.getLogger(__name__)

AUTH_STATE_FILE = "data/instagram_auth_state.json"
SESSION_SETTINGS_FILE = "data/instagram_session_settings.json"


class InstagrapiActions:
    """Instagram actions via instagrapi mobile API client."""

    def __init__(
        self,
        auth_state_file: str = AUTH_STATE_FILE,
        session_settings_file: str = SESSION_SETTINGS_FILE,
        proxy: str = "",
        username: str = "",
        password: str = "",
        switch_to: str = "",
    ):
        self.auth_state_file = auth_state_file
        self.session_settings_file = session_settings_file
        self._username = username
        self._password = password
        self._switch_to = switch_to
        self.client = Client()
        self.client.delay_range = [1, 3]
        if proxy:
            self.client.set_proxy(proxy)
            logger.info("Instagram: using proxy %s", proxy.split("@")[-1] if "@" in proxy else proxy)

    def _load_sessionid(self) -> str:
        """Load sessionid from auth state JSON file.

        Supports two formats:
        - Playwright storage state: {"cookies": [{"name": "sessionid", "value": "..."}]}
        - Simple format: {"sessionid": "..."}
        """
        if not os.path.exists(self.auth_state_file):
            raise FileNotFoundError(
                f"Instagram auth state file not found: {self.auth_state_file}"
            )
        with open(self.auth_state_file, "r") as f:
            data = json.load(f)

        raw_sessionid = ""

        # Try Playwright cookie format first
        if "cookies" in data:
            for cookie in data["cookies"]:
                if cookie.get("name") == "sessionid":
                    raw_sessionid = cookie.get("value", "")
                    break

        # Fall back to simple {"sessionid": "..."} format
        if not raw_sessionid:
            raw_sessionid = data.get("sessionid", "")

        if not raw_sessionid:
            raise ValueError("sessionid not found in auth state file")
        # URL-decode the sessionid (instagrapi expects the decoded form)
        return unquote(raw_sessionid)

    def login(self) -> bool:
        """Login to Instagram. Tries saved session, then username/password, then sessionid."""
        try:
            # 1. Try to restore a saved session
            if os.path.exists(self.session_settings_file):
                try:
                    self.client.load_settings(self.session_settings_file)
                    self.client.login(self._username, self._password) if self._username else None
                    if self.is_logged_in():
                        logger.info("Instagram: restored saved session")
                        return True
                except Exception as e:
                    logger.warning("Instagram: saved session failed: %s", e)

            # 2. Login with username/password (creates session on proxy IP)
            if self._username and self._password:
                try:
                    self.client.login(self._username, self._password)
                except (KeyError, TypeError) as e:
                    logger.warning("Instagram: login parse warning: %s", e)
                except Exception as e:
                    logger.warning("Instagram: username/password login failed: %s", e)

                # Switch to linked account if needed
                if self._switch_to and self.is_logged_in():
                    try:
                        user_id = self.client.user_id_from_username(self._switch_to)
                        self.client.switch_to_account(user_id)
                        logger.info("Instagram: switched to @%s", self._switch_to)
                    except AttributeError:
                        # switch_to_account may not exist — try alternative
                        logger.warning("Instagram: switch_to_account not available, using direct relogin")
                        try:
                            user_id = self.client.user_id_from_username(self._switch_to)
                            self.client.user_id = user_id
                            self.client.username = self._switch_to
                            logger.info("Instagram: set active account to @%s", self._switch_to)
                        except Exception as e2:
                            logger.error("Instagram: failed to switch account: %s", e2)
                    except Exception as e:
                        logger.error("Instagram: failed to switch to @%s: %s", self._switch_to, e)

                if self.is_logged_in():
                    self.save_session()
                    logger.info("Instagram: logged in as %s", self._switch_to or self._username)
                    return True

            # 3. Fallback to sessionid
            try:
                sessionid = self._load_sessionid()
                self.client.login_by_sessionid(sessionid)
                if self.is_logged_in():
                    self.save_session()
                    logger.info("Instagram: logged in via sessionid")
                    return True
            except (KeyError, TypeError) as e:
                logger.warning("Instagram: sessionid parse warning: %s", e)
                if self.is_logged_in():
                    self.save_session()
                    return True
            except Exception as e:
                logger.warning("Instagram: sessionid login failed: %s", e)

            logger.error("Instagram: all login methods failed")
            return False
        except Exception as e:
            logger.error("Instagram: login failed: %s", e)
            return False

    def save_session(self):
        """Persist session settings to disk for reuse."""
        try:
            self.client.dump_settings(self.session_settings_file)
            logger.info("Instagram: session settings saved to %s", self.session_settings_file)
        except Exception as e:
            logger.warning("Instagram: failed to save session settings: %s", e)

    def is_logged_in(self) -> bool:
        """Check if the client is authenticated."""
        try:
            self.client.account_info()
            return True
        except Exception:
            return False

    def post_image(self, image_path: str, caption: str) -> dict | None:
        """Upload a photo post. Returns media dict on success, None on failure."""
        try:
            media = self.client.photo_upload(Path(image_path), caption)
            logger.info("Instagram: image posted — media_id=%s", media.id)
            return {"media_id": str(media.id), "code": media.code}
        except FeedbackRequired as e:
            logger.error("Instagram: post blocked by spam filter: %s", e)
            return None
        except PleaseWaitFewMinutes as e:
            logger.error("Instagram: rate limited, please wait: %s", e)
            return None
        except Exception as e:
            logger.error("Instagram: failed to post image: %s", e)
            return None

    def post_video(self, video_path: str, caption: str) -> dict | None:
        """Upload a Reel (clip). Returns media dict on success, None on failure."""
        try:
            media = self.client.clip_upload(Path(video_path), caption)
            logger.info("Instagram: reel posted — media_id=%s", media.id)
            return {"media_id": str(media.id), "code": media.code}
        except FeedbackRequired as e:
            logger.error("Instagram: reel blocked by spam filter: %s", e)
            return None
        except PleaseWaitFewMinutes as e:
            logger.error("Instagram: rate limited, please wait: %s", e)
            return None
        except Exception as e:
            logger.error("Instagram: failed to post reel: %s", e)
            return None

    def like_post(self, media_id: str) -> bool:
        """Like a post by media_id."""
        try:
            self.client.media_like(media_id)
            logger.info("Instagram: liked media %s", media_id)
            return True
        except Exception as e:
            logger.error("Instagram: failed to like media %s: %s", media_id, e)
            return False

    def comment_on_post(self, media_id: str, text: str) -> bool:
        """Comment on a post by media_id."""
        try:
            comment = self.client.media_comment(media_id, text)
            logger.info("Instagram: commented on media %s (comment_id=%s)", media_id, comment.pk)
            return True
        except FeedbackRequired as e:
            logger.error("Instagram: comment blocked by spam filter: %s", e)
            return False
        except Exception as e:
            logger.error("Instagram: failed to comment on media %s: %s", media_id, e)
            return False

    def get_feed_posts(self, amount: int = 10) -> list:
        """Get posts from the user's timeline feed."""
        try:
            return self.client.get_timeline_feed()[:amount]
        except Exception as e:
            logger.error("Instagram: failed to get feed: %s", e)
            return []

    def get_user_media(self, username: str, amount: int = 5) -> list:
        """Get recent media from a specific user."""
        try:
            user_id = self.client.user_id_from_username(username)
            return self.client.user_medias(user_id, amount=amount)
        except Exception as e:
            logger.error("Instagram: failed to get media for @%s: %s", username, e)
            return []

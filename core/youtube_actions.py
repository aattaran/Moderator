"""YouTube Shorts upload via YouTube Data API v3."""

import http.client
import logging
import os
import random
import time

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]


class YouTubeActions:
    """Upload YouTube Shorts via the Data API v3."""

    def __init__(
        self,
        client_secrets_file: str = "data/youtube_client_secrets.json",
        credentials_file: str = "data/youtube_credentials.json",
    ):
        self.client_secrets_file = client_secrets_file
        self.credentials_file = credentials_file
        self._service = None

    def _get_service(self):
        """Get authenticated YouTube API service, refreshing token if needed."""
        if self._service:
            return self._service

        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"YouTube credentials not found: {self.credentials_file}. "
                "Run: python scripts/youtube_auth.py"
            )

        credentials = Credentials.from_authorized_user_file(self.credentials_file, SCOPES)

        if credentials.expired:
            if credentials.refresh_token:
                credentials.refresh(Request())
                with open(self.credentials_file, "w") as f:
                    f.write(credentials.to_json())
                logger.info("YouTube: refreshed access token")
            else:
                raise RuntimeError(
                    "YouTube credentials expired and no refresh_token available. "
                    "Re-run: python scripts/youtube_auth.py"
                )

        self._service = build("youtube", "v3", credentials=credentials)
        return self._service

    def is_authenticated(self) -> bool:
        """Check if valid credentials exist."""
        try:
            self._get_service()
            return True
        except Exception as e:
            logger.warning("YouTube: not authenticated: %s", e)
            return False

    def upload_short(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        privacy_status: str = "public",
    ) -> dict | None:
        """Upload a video as a YouTube Short.

        Returns {"video_id": "...", "url": "..."} on success, None on failure.
        """
        if not os.path.exists(video_path):
            logger.error("YouTube: video file not found: %s", video_path)
            return None

        # Ensure #Shorts in title
        if "#Shorts" not in title and "#shorts" not in title.lower():
            title = f"{title} #Shorts"

        # Truncate title to 100 chars
        if len(title) > 100:
            title = title[:96] + " #Shorts" if "#Shorts" not in title[:96] else title[:100]

        if tags is None:
            tags = []
        if "Shorts" not in tags:
            tags.append("Shorts")

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            chunksize=8 * 1024 * 1024,  # 8MB chunks — Google recommends ≥1MB
            resumable=True,
        )

        try:
            service = self._get_service()
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = self._resumable_upload(request)
            if response and "id" in response:
                video_id = response["id"]
                url = f"https://youtube.com/shorts/{video_id}"
                logger.info("YouTube: uploaded Short — %s", url)
                return {"video_id": video_id, "url": url}

        except HttpError as e:
            logger.error("YouTube: upload HTTP error: %s", e)
        except Exception as e:
            logger.error("YouTube: upload failed: %s", e)

        return None

    def _resumable_upload(self, request) -> dict | None:
        """Execute resumable upload with exponential backoff."""
        response = None
        retry = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.debug("YouTube: upload %d%% complete", int(status.progress() * 100))
            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    retry += 1
                    if retry > MAX_RETRIES:
                        logger.error("YouTube: max retries exceeded")
                        return None
                    sleep_time = random.uniform(1, 2 ** retry)
                    logger.warning("YouTube: retry %d/%d in %.1fs", retry, MAX_RETRIES, sleep_time)
                    time.sleep(sleep_time)
                else:
                    raise
            except (httplib2.HttpLib2Error, IOError, http.client.HTTPException) as e:
                retry += 1
                if retry > MAX_RETRIES:
                    logger.error("YouTube: max retries exceeded")
                    return None
                sleep_time = random.uniform(1, 2 ** retry)
                logger.warning("YouTube: network error, retry %d/%d: %s", retry, MAX_RETRIES, e)
                time.sleep(sleep_time)

        return response

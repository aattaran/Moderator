"""comments-song.app HTTP client — free-text submission + status polling + song fetch.

Used by the comments-song -> Shorts -> YouTube pipeline. Reproduces the worker's
styleHash() so polling URLs can be constructed without a separate round-trip.

The styleHash() reproduction must stay in sync with
packages/shared/src/style-hash.ts in the comments-song repo. AUTO mode hashes
the literal string "auto"; explicit specs are serialized via the documented
key order. The slice(0,16) on the SHA-256 hex matches the worker.

CSRF: state-changing requests (POST/PUT/PATCH/DELETE) MUST carry an Origin
header matching the worker's PUBLIC_ORIGIN env var (defaults to
https://comments-song.app). The middleware is in apps/worker/src/index.ts
(`CSRF_NO_ORIGIN`). Browsers send Origin automatically; server-to-server
clients do not. This client derives Origin from base_url and applies it on
every request — this is a protection requirement, not optional.

Song JSON shape note (for Step 3 metadata builder, future-reader bait):
the canonical YouTube-facing title is `song.lyrics.title` ("Tokyo Neon Rain"),
NOT `song.sourceVideo.title` (which for free-text is the truncated raw prompt).
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://comments-song.app"
AUTO_STYLE_SENTINEL = "auto"
STYLE_KEY_ORDER = ("genre", "mood", "tempo", "vocals", "quoteLevel")

TERMINAL_STATUSES = frozenset({"done", "failed"})
RETRIABLE_STATUS_CODES = frozenset({500, 502, 503, 504})


def style_hash(spec: dict[str, Any] | None = None) -> str:
    """Reproduce packages/shared/src/style-hash.ts.

    AUTO mode (spec is None) hashes the literal string 'auto'.
    An explicit spec is serialized as JSON with the documented key order;
    keys whose value is None are dropped, matching JS's JSON.stringify
    behavior when a property is `undefined` under a replacer-array.
    """
    if spec is None or spec == AUTO_STYLE_SENTINEL:
        canonical = "auto"
    else:
        ordered = {k: spec[k] for k in STYLE_KEY_ORDER if spec.get(k) is not None}
        canonical = json.dumps(ordered, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class CommentsSongError(RuntimeError):
    """Base error for comments-song client failures."""


class CommentsSongRejected(CommentsSongError):
    """4xx response from the API — the request itself was bad."""


class CommentsSongFailed(CommentsSongError):
    """The pipeline reached terminal status='failed'."""


class CommentsSongTimeout(CommentsSongError):
    """wait_for_done exceeded its wall-clock budget."""


class CommentsSongClient:
    """Client for comments-song.app submission + polling.

    Single instance is cheap; the underlying httpx.AsyncClient is created per
    request, which matches the Kling client pattern in this repo. Switch to a
    persistent client only if a profiling-driven reason emerges.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        # CSRF middleware in apps/worker/src/index.ts rejects state-changing
        # requests without an Origin matching PUBLIC_ORIGIN. Browsers send
        # this automatically; server-to-server clients don't. Derive from
        # base_url so a tunnel/staging override stays consistent.
        self._headers = {"Origin": self.base_url}

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One request with retry on network/5xx; raises on 4xx and exhausted retries."""
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method == "POST":
                        resp = await client.post(url, json=json_body, headers=self._headers)
                    elif method == "GET":
                        resp = await client.get(url, headers=self._headers)
                    else:
                        raise ValueError(f"unsupported method: {method}")
            except (httpx.NetworkError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < self.max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "comments-song %s %s: network error (retry %d/%d in %ds): %s",
                        method, path, attempt + 1, self.max_retries, wait, e,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise CommentsSongError(
                    f"comments-song {method} {path}: network error after "
                    f"{self.max_retries} retries: {e}"
                ) from e

            if resp.status_code in RETRIABLE_STATUS_CODES and attempt < self.max_retries:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "comments-song %s %s: HTTP %d (retry %d/%d in %ds)",
                    method, path, resp.status_code, attempt + 1, self.max_retries, wait,
                )
                await asyncio.sleep(wait)
                continue

            if 400 <= resp.status_code < 500:
                # Don't retry; surface the worker's structured error if there is one.
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {"error": "unparseable", "raw": resp.text[:500]}
                raise CommentsSongRejected(
                    f"comments-song {method} {path}: HTTP {resp.status_code} {err_body}"
                )

            if resp.status_code >= 500:
                raise CommentsSongError(
                    f"comments-song {method} {path}: HTTP {resp.status_code} "
                    f"after {self.max_retries} retries"
                )

            return resp.json()

        raise CommentsSongError(
            f"comments-song {method} {path}: exhausted retries (last: {last_exc})"
        )

    async def submit_freetext(
        self,
        prompt: str,
        style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/songs with a free-text prompt.

        Returns {videoId, generationId, status, cached, ...}.
        Raises CommentsSongRejected on 4xx (e.g. flag off -> 404, prompt too short -> 400).
        """
        body: dict[str, Any] = {"prompt": prompt}
        if style is not None:
            body["style"] = style
        resp = await self._request("POST", "/api/songs", json_body=body)
        logger.info(
            "comments-song: submitted prompt (%d chars) -> videoId=%s status=%s cached=%s",
            len(prompt), resp.get("videoId"), resp.get("status"), resp.get("cached"),
        )
        return resp

    async def poll_status(self, video_id: str, style_hash_hex: str) -> dict[str, Any]:
        """GET /api/songs/:videoId/:styleHash/status.

        Returns {status, callbackState, etaSeconds, error?}.
        """
        return await self._request(
            "GET", f"/api/songs/{video_id}/{style_hash_hex}/status"
        )

    async def get_song(self, video_id: str, style_hash_hex: str) -> dict[str, Any]:
        """GET /api/songs/:videoId/:styleHash — full song JSON.

        Returns: {videoId, styleHash, status, generationId, durationSeconds,
                  audio: {r2Key, contentType}, audioUrl, artworkUrl,
                  lyrics: {title, sections: [{kind, lines: [{text, startMs}]}]},
                  actualStyle, sourceType, ...}.

        Notes for callers:
        - `lyrics.title` is the canonical song title (use it for YouTube uploads).
        - `artworkUrl` MAY be null even when status='done' — cover-art arrives via
          a separate KIE callback, async to audio. Re-fetch later if you need it.
        - `audioUrl` is HMAC-signed with ~1h TTL.
        """
        return await self._request(
            "GET", f"/api/songs/{video_id}/{style_hash_hex}"
        )

    async def wait_for_done(
        self,
        video_id: str,
        style_hash_hex: str,
        timeout_sec: float = 480.0,
        poll_interval_sec: float = 5.0,
    ) -> dict[str, Any]:
        """Poll until status reaches a terminal state, then fetch full song JSON.

        Returns the full song JSON on success.
        Raises CommentsSongFailed on terminal status='failed'.
        Raises CommentsSongTimeout if the wall-clock budget is exceeded.
        """
        start = time.time()
        last_status: str | None = None
        while time.time() - start < timeout_sec:
            status_resp = await self.poll_status(video_id, style_hash_hex)
            status = status_resp.get("status")

            if status != last_status:
                logger.info(
                    "comments-song: %s/%s status=%s eta=%ss",
                    video_id, style_hash_hex, status, status_resp.get("etaSeconds"),
                )
                last_status = status

            if status == "done":
                return await self.get_song(video_id, style_hash_hex)
            if status == "failed":
                err = status_resp.get("error") or {}
                raise CommentsSongFailed(
                    f"comments-song: {video_id}/{style_hash_hex} failed at "
                    f"stage={err.get('stage')} code={err.get('code')} "
                    f"retryable={err.get('retryable')}"
                )

            await asyncio.sleep(poll_interval_sec)

        raise CommentsSongTimeout(
            f"comments-song: {video_id}/{style_hash_hex} timed out after "
            f"{timeout_sec}s (last status: {last_status})"
        )

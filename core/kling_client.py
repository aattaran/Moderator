"""Kling AI API client — JWT auth, image-to-video, task polling, lip sync."""

import asyncio
import base64
import logging
import time
from pathlib import Path

import httpx
import jwt

logger = logging.getLogger(__name__)

BASE_URL = "https://api-singapore.klingai.com"


class KlingClient:
    """Direct Kling API client with JWT authentication."""

    def __init__(self, access_key: str, secret_key: str):
        if not access_key or not secret_key:
            raise ValueError("KLING_ACCESS_KEY_ID and KLING_SECRET_KEY required")
        self._access_key = access_key
        self._secret_key = secret_key
        self._token: str | None = None
        self._token_expires: float = 0

    def _get_token(self) -> str:
        """Generate JWT token (cached for 25 minutes)."""
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token

        payload = {
            "iss": self._access_key,
            "exp": int(now + 1800),  # 30 minutes
            "nbf": int(now - 5),     # 5 seconds ago
        }
        self._token = jwt.encode(payload, self._secret_key, algorithm="HS256")
        self._token_expires = now + 1500  # Refresh after 25 minutes
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    async def _post(self, endpoint: str, body: dict, retries: int = 3) -> dict:
        """POST request to Kling API with retry on 5xx, network errors, and 429."""
        url = f"{BASE_URL}{endpoint}"
        # 429 backoff: 60s / 120s / 180s — long enough for Kling's per-minute quota window.
        _429_waits = [60, 120, 180]
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(retries):
                try:
                    resp = await client.post(url, json=body, headers=self._headers())
                except (httpx.NetworkError, httpx.TimeoutException) as e:
                    if attempt < retries - 1:
                        wait = 2 ** (attempt + 1)
                        logger.warning("Kling: network error on %s (retry %d/%d in %ds): %s", endpoint, attempt + 1, retries, wait, e)
                        await asyncio.sleep(wait)
                        continue
                    raise
                if resp.status_code == 429:
                    # code 1102 = account balance exhausted — retrying won't help.
                    # Use a separate variable to avoid overwriting the original request body.
                    try:
                        err_body = resp.json()
                    except Exception:
                        err_body = {}
                    if err_body.get("code") == 1102:
                        raise RuntimeError("Kling account balance exhausted (code 1102) — top up at klingai.com")
                    if attempt < retries - 1:
                        # Respect Retry-After header if present, else use fixed backoff schedule.
                        retry_after = resp.headers.get("Retry-After")
                        try:
                            wait = int(retry_after) if retry_after else _429_waits[attempt]
                        except ValueError:
                            wait = _429_waits[attempt]
                        logger.warning(
                            "Kling 429 rate-limited on %s — waiting %ds (retry %d/%d)",
                            endpoint, wait, attempt + 1, retries,
                        )
                        await asyncio.sleep(wait)
                        continue
                    # All retries exhausted on 429 — raise a clean error, not the raw HTTP exception.
                    raise RuntimeError(
                        f"Kling API rate-limited on {endpoint} after {retries} attempts "
                        f"(HTTP 429). Wait a few minutes before retrying."
                    )
                if resp.status_code >= 500 and attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Kling API %s: %s (retry %d/%d in %ds)", resp.status_code, endpoint, attempt + 1, retries, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    logger.error("Kling API %s: %s — %s", resp.status_code, endpoint, resp.text[:500])
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"Kling API error: {data.get('message', data)}")
                return data
        raise RuntimeError(f"Kling API: {endpoint} failed after {retries} retries")

    async def _get(self, endpoint: str) -> dict:
        """GET request to Kling API."""
        url = f"{BASE_URL}{endpoint}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Kling API error: {data.get('message', data)}")
            return data

    # ── Image to Video ────────────────────────────────────────

    async def image_to_video(
        self,
        image: str,
        prompt: str,
        model_name: str = "kling-v3",
        mode: str = "pro",
        duration: str = "5",
        aspect_ratio: str = "9:16",
        negative_prompt: str = "",
        cfg_scale: float = 0.5,
        sound: str = "on",
    ) -> str:
        """Submit image-to-video generation. Returns task_id.

        Args:
            image: URL or base64-encoded image data
            prompt: Motion/action description
            model_name: "kling-v1-6", "kling-v2-master", "kling-v3"
            mode: "std" or "pro" (V3 Pro recommended)
            duration: "5" or "10" seconds
            aspect_ratio: "16:9", "9:16", "1:1"
            negative_prompt: Elements to exclude
            cfg_scale: Prompt adherence (0-1)
            sound: "on" or "off" — native audio generation
        """
        body = {
            "model_name": model_name,
            "image": image,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "cfg_scale": cfg_scale,
        }
        if mode:
            body["mode"] = mode
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if sound:
            body["sound"] = sound

        resp = await self._post("/v1/videos/image2video", body)
        task_id = resp["data"]["task_id"]
        logger.info("Kling: image-to-video task submitted: %s (model=%s, mode=%s)", task_id, model_name, mode)
        return task_id

    async def image_to_video_from_file(
        self,
        image_path: str,
        prompt: str,
        **kwargs,
    ) -> str:
        """Submit image-to-video from a local file. Returns task_id.

        Sends image as raw base64 (no data URI prefix) — Kling API expects this format.
        """
        path = Path(image_path)
        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        return await self.image_to_video(image=b64, prompt=prompt, **kwargs)

    # ── Task Status / Polling ─────────────────────────────────

    async def get_task(self, task_id: str) -> dict:
        """Check task status. Returns full task data."""
        resp = await self._get(f"/v1/videos/image2video/{task_id}")
        return resp["data"]

    async def poll_until_complete(
        self, task_id: str, poll_interval: float = 10.0, timeout: float = 600.0
    ) -> dict:
        """Poll task until complete. Returns dict with 'url', 'id', 'duration'.

        Raises RuntimeError on failure or timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            task = await self.get_task(task_id)
            status = task.get("task_status", "")

            if status == "succeed":
                videos = task.get("task_result", {}).get("videos", [])
                if videos:
                    v = videos[0]
                    result = {
                        "url": v.get("url", ""),
                        "id": v.get("id", ""),
                        "duration": v.get("duration", 0),
                    }
                    logger.info("Kling: video ready — %ss, id=%s", result["duration"], result["id"])
                    return result
                raise RuntimeError("Kling: task succeeded but no video data")

            if status == "failed":
                msg = task.get("task_status_msg", "unknown error")
                raise RuntimeError(f"Kling: video generation failed — {msg}")

            elapsed = int(time.time() - start)
            if elapsed % 30 == 0:
                logger.info("Kling: task %s still generating... (%ds)", task_id, elapsed)
            await asyncio.sleep(poll_interval)

        raise RuntimeError(f"Kling: task {task_id} timed out after {timeout}s")

    # ── Download ──────────────────────────────────────────────

    async def download_video(self, video_url: str, output_path: str) -> Path:
        """Download video from URL to local file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        logger.info("Kling: downloaded video to %s (%d bytes)", path, path.stat().st_size)
        return path

    # ── Lip Sync (two-step: identify faces → sync) ─────────

    async def identify_faces(self, video_url: str) -> list[dict]:
        """Identify faces in a video. Returns list of face data."""
        resp = await self._post("/v1/videos/identify-face", {"video_url": video_url})
        faces = resp.get("data", {}).get("face_list", [])
        logger.info("Kling: identified %d faces in video", len(faces))
        return faces

    async def lip_sync(self, video_url: str, audio_url: str) -> str:
        """Full lip sync: identify face → submit sync with faceChoose. Returns task_id."""
        # Step 1: identify faces
        faces = await self.identify_faces(video_url)
        if not faces:
            raise RuntimeError("Kling: no faces detected in video — cannot lip sync")

        face = faces[0]  # Use first detected face
        face_id = face.get("face_id", face.get("id", ""))

        # Step 2: submit lip sync with face selection
        body = {
            "video_url": video_url,
            "face_choose": [{
                "face_id": face_id,
                "audio_url": audio_url,
            }],
        }
        resp = await self._post("/v1/videos/advanced-lip-sync", body)
        task_id = resp["data"]["task_id"]
        logger.info("Kling: lip sync task submitted: %s (face_id=%s)", task_id, face_id)
        return task_id

    async def get_lip_sync_task(self, task_id: str) -> dict:
        """Check lip sync task status."""
        resp = await self._get(f"/v1/videos/advanced-lip-sync/{task_id}")
        return resp["data"]

    async def poll_lip_sync(self, task_id: str, timeout: float = 300.0) -> str:
        """Poll lip sync task until complete. Returns video URL."""
        start = time.time()
        while time.time() - start < timeout:
            task = await self.get_lip_sync_task(task_id)
            status = task.get("task_status", "")

            if status == "succeed":
                videos = task.get("task_result", {}).get("videos", [])
                if videos:
                    return videos[0].get("url", "")
                raise RuntimeError("Kling: lip sync succeeded but no video URL")

            if status == "failed":
                raise RuntimeError(f"Kling: lip sync failed — {task.get('task_status_msg')}")

            await asyncio.sleep(10)

        raise RuntimeError(f"Kling: lip sync timed out after {timeout}s")

    # ── Video Extension ───────────────────────────────────────

    async def extend_video(self, video_id: str, prompt: str = "", negative_prompt: str = "") -> str:
        """Extend a video from the last frame. Returns task_id.

        Args:
            video_id: The video ID from a previous generation (NOT the URL).
            prompt: Motion-only prompt for the extension.
            negative_prompt: Elements to exclude.
        """
        body = {"video_id": video_id}
        if prompt:
            body["prompt"] = prompt
        if negative_prompt:
            body["negative_prompt"] = negative_prompt

        resp = await self._post("/v1/videos/video-extend", body)
        task_id = resp["data"]["task_id"]
        logger.info("Kling: video extension submitted: %s (from video_id=%s)", task_id, video_id)
        return task_id

    async def poll_extend(self, task_id: str, poll_interval: float = 10.0, timeout: float = 600.0) -> dict:
        """Poll video extension task. Returns dict with 'url', 'id', 'duration'."""
        start = time.time()
        while time.time() - start < timeout:
            resp = await self._get(f"/v1/videos/video-extend/{task_id}")
            task = resp["data"]
            status = task.get("task_status", "")

            if status == "succeed":
                videos = task.get("task_result", {}).get("videos", [])
                if videos:
                    v = videos[0]
                    result = {
                        "url": v.get("url", ""),
                        "id": v.get("id", ""),
                        "duration": v.get("duration", 0),
                    }
                    logger.info("Kling: extension ready — %ds, id=%s", result["duration"], result["id"])
                    return result
                raise RuntimeError("Kling: extension succeeded but no video data")

            if status == "failed":
                raise RuntimeError(f"Kling: extension failed — {task.get('task_status_msg')}")

            elapsed = int(time.time() - start)
            if elapsed % 30 == 0:
                logger.info("Kling: extension %s still generating... (%ds)", task_id, elapsed)
            await asyncio.sleep(poll_interval)

        raise RuntimeError(f"Kling: extension {task_id} timed out after {timeout}s")

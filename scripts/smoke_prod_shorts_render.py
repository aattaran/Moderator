"""End-to-end production smoke test for the server-rendered Shorts pipeline.

Submits a fresh free-text prompt, polls for status='done' + artworkUrl,
then waits for the Container to flip shorts_video_status to 'done', then
fetches the rendered MP4 and saves a frame for Convention #7 inspection.

Usage:
    python scripts/smoke_prod_shorts_render.py
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from core.comments_song_actions import (  # noqa: E402
    CommentsSongClient,
    CommentsSongError,
    style_hash,
)

import httpx  # noqa: E402

OUT_DIR = ROOT / "data" / "prod_smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Unique-ish prompt so we exercise the full pipeline (no cache-hit).
PROMPT = (
    "a chill bossa nova about a quiet sunday morning "
    "with coffee on a balcony in lisbon"
)


async def wait_for_shorts_done(
    client: CommentsSongClient,
    video_id: str,
    s_hash: str,
    timeout_sec: float = 300.0,
    poll_interval_sec: float = 5.0,
) -> dict:
    """Poll get_song until shortsVideoStatus='done'."""
    start = time.time()
    last_status = None
    while time.time() - start < timeout_sec:
        song = await client.get_song(video_id, s_hash)
        status = song.get("shortsVideoStatus")
        if status != last_status:
            elapsed = int(time.time() - start)
            logging.info(
                "shorts: %s/%s status=%s elapsed=%ds (url=%s)",
                video_id, s_hash, status, elapsed, bool(song.get("shortsVideoUrl")),
            )
            last_status = status
        if status == "done" and song.get("shortsVideoUrl"):
            return song
        if status == "failed":
            raise RuntimeError(
                f"shorts render failed: {song.get('shortsVideoLastError') or 'unknown'}"
            )
        await asyncio.sleep(poll_interval_sec)
    raise RuntimeError(
        f"shorts render did not complete within {timeout_sec}s "
        f"(last status: {last_status})"
    )


def ffprobe_streams(path: Path) -> dict:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        text=True,
    )
    return json.loads(out)


def extract_frame(video: Path, at_sec: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["ffmpeg", "-y", "-ss", str(at_sec), "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def main() -> int:
    client = CommentsSongClient()
    s_hash = style_hash(None)

    print(f"\n[1] SUBMIT — prompt={PROMPT!r}")
    try:
        resp = await client.submit_freetext(PROMPT)
    except CommentsSongError as e:
        print(f"  FAIL: {e}")
        return 1
    video_id = resp["videoId"]
    print(f"  -> videoId={video_id} status={resp.get('status')} cached={resp.get('cached')}")

    print(f"\n[2] POLL — wait for status=done + artworkUrl ready")
    if resp.get("cached") and resp.get("status") == "done":
        song = await client.get_song(video_id, s_hash)
    else:
        song = await client.wait_for_done(video_id, s_hash, timeout_sec=600)
    print(f"  -> status=done lyrics.title={(song.get('lyrics') or {}).get('title')!r}")

    if not song.get("artworkUrl"):
        print(f"  -> waiting for artworkUrl (cover-art callback)...")
        artwork_start = time.time()
        while not song.get("artworkUrl") and time.time() - artwork_start < 180:
            await asyncio.sleep(5)
            song = await client.get_song(video_id, s_hash)
        if not song.get("artworkUrl"):
            print(f"  FAIL: artworkUrl never arrived")
            return 1
    print(f"  -> artworkUrl ready")

    print(f"\n[3] WAIT FOR SHORTS — poll shortsVideoStatus='done'")
    print(f"  (Container takes a few minutes to provision after first deploy.)")
    try:
        song = await wait_for_shorts_done(client, video_id, s_hash, timeout_sec=600)
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        return 1

    shorts_url = song.get("shortsVideoUrl")
    print(f"  -> shortsVideoStatus=done shortsVideoUrl={shorts_url[:120] if shorts_url else None!r}")

    print(f"\n[4] DOWNLOAD MP4 — fetching the signed Shorts URL")
    mp4_path = OUT_DIR / f"{video_id}_{s_hash}.mp4"
    async with httpx.AsyncClient(timeout=120.0) as h:
        r = await h.get(shorts_url, follow_redirects=True)
        if r.status_code != 200:
            print(f"  FAIL: HTTP {r.status_code} fetching shorts URL")
            return 1
        mp4_path.write_bytes(r.content)
    size_mb = mp4_path.stat().st_size / (1024 * 1024)
    print(f"  -> saved {mp4_path} ({size_mb:.2f} MB)")

    print(f"\n[5] FFPROBE — container + stream sanity")
    try:
        meta = ffprobe_streams(mp4_path)
    except subprocess.CalledProcessError as e:
        print(f"  FAIL: ffprobe error {e}")
        return 1
    fmt = meta.get("format") or {}
    streams = meta.get("streams") or []
    print(f"  container: {fmt.get('format_long_name')}")
    print(f"  duration:  {fmt.get('duration')}s")
    print(f"  bit_rate:  {fmt.get('bit_rate')}")
    video_s = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_s = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video_s:
        print(f"  video: codec={video_s.get('codec_name')} dims={video_s.get('width')}x{video_s.get('height')} fps={video_s.get('r_frame_rate')}")
    if audio_s:
        print(f"  audio: codec={audio_s.get('codec_name')} sr={audio_s.get('sample_rate')} ch={audio_s.get('channels')}")

    print(f"\n[6] FRAME — extract t=mid for Convention #7 visual inspection")
    duration = float(fmt.get("duration") or 0)
    at_sec = max(2.0, duration / 2)
    frame_path = OUT_DIR / f"{video_id}_{s_hash}_frame_t{int(at_sec)}s.png"
    try:
        extract_frame(mp4_path, at_sec, frame_path)
        print(f"  -> saved {frame_path}")
    except subprocess.CalledProcessError as e:
        print(f"  FAIL: ffmpeg extract error {e}")

    print(f"\n[7] GATE CHECKS")
    checks = [
        (">5MB MP4", mp4_path.stat().st_size > 5 * 1024 * 1024),
        ("video stream present", video_s is not None),
        ("audio stream present", audio_s is not None),
        (
            "video is 1080x1920 (9:16)",
            video_s is not None and video_s.get("width") == 1080 and video_s.get("height") == 1920,
        ),
        (
            "duration matches song (~150s ±5)",
            fmt.get("duration") is not None
            and abs(float(fmt["duration"]) - (song.get("durationSeconds") or 150)) < 5.0,
        ),
    ]
    for name, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}")

    print(f"\n[8] ARTIFACTS")
    print(f"  MP4: {mp4_path}")
    print(f"  PNG: {frame_path}")
    print(f"  videoId / styleHash: {video_id} / {s_hash}")
    print(f"  song page: https://comments-song.app/v/{video_id}/{s_hash}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

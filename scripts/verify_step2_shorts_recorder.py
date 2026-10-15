"""Step 2 verification — drive the comments-song Shorts compositor in headless
Chromium for a known-done song, save the MP4, and inspect.

Inspection is automated per CLAUDE.md convention #7: don't trust file-size
alone. We probe the container with ffprobe (codecs, dimensions, duration,
stream count) AND extract one frame at mid-song to a PNG so the actual
artwork + lyric overlay are inspectable.

Usage:
    python scripts/verify_step2_shorts_recorder.py
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

from core.shorts_recorder import record_song  # noqa: E402

# A known-done song with artwork populated (verified via Step 1).
SONG_URL = "https://comments-song.app/v/ft_b619a68e0cc6e890/929260ad9b9ea9fe"
OUT_DIR = ROOT / "data" / "step2_outputs"
OUT_PATH = OUT_DIR / "Tokyo_Neon_Rain.mp4"
# Lyric line "Gray clouds swallowing the electric light" starts at 40_632ms.
# A frame around 45s should show artwork + that line.
FRAME_AT_SEC = 45


def ffprobe_streams(path: Path) -> dict:
    """Run ffprobe and return parsed JSON metadata."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)


def extract_frame(video_path: Path, at_sec: float, out_path: Path) -> None:
    """Extract a single frame at at_sec from video_path to out_path (PNG)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "ffmpeg", "-y",
            "-ss", str(at_sec),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(out_path),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1] Driving comments-song Shorts export")
    print(f"    URL: {SONG_URL}")
    print(f"    Output: {OUT_PATH}")
    print(f"    (recording is real-time — expect ~2:30 wall clock for this song)")

    t0 = time.time()
    try:
        saved = await record_song(SONG_URL, OUT_PATH)
    except Exception as e:
        print(f"\n[1] FAIL: {type(e).__name__}: {e}")
        return 1
    elapsed = time.time() - t0

    size_bytes = saved.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"\n[2] Recorded in {elapsed:.1f}s ({elapsed / 60:.1f}min) — {size_mb:.2f} MB")

    print(f"\n[3] ffprobe — container + stream inspection")
    try:
        meta = ffprobe_streams(saved)
    except subprocess.CalledProcessError as e:
        print(f"    ffprobe failed: {e}")
        return 1

    fmt = meta.get("format", {})
    print(f"    container: {fmt.get('format_long_name')}")
    print(f"    duration:  {fmt.get('duration')}s")
    print(f"    bit_rate:  {fmt.get('bit_rate')}")
    streams = meta.get("streams", [])
    print(f"    streams:   {len(streams)}")
    video_stream = None
    audio_stream = None
    for s in streams:
        ctype = s.get("codec_type")
        codec = s.get("codec_name")
        if ctype == "video":
            video_stream = s
            print(
                f"      video: {codec}  {s.get('width')}x{s.get('height')}  "
                f"r_frame_rate={s.get('r_frame_rate')}  pix_fmt={s.get('pix_fmt')}"
            )
        elif ctype == "audio":
            audio_stream = s
            print(
                f"      audio: {codec}  sample_rate={s.get('sample_rate')}  "
                f"channels={s.get('channels')}  bit_rate={s.get('bit_rate')}"
            )

    print(f"\n[4] Extracting frame at t={FRAME_AT_SEC}s (lyric line should be visible)")
    frame_path = OUT_DIR / f"frame_t{FRAME_AT_SEC}s.png"
    try:
        extract_frame(saved, FRAME_AT_SEC, frame_path)
        print(f"    saved: {frame_path}")
    except subprocess.CalledProcessError as e:
        print(f"    ffmpeg extract failed: {e}")

    print(f"\n[5] Step 2 gate checks:")
    checks = [
        (">5MB file size", size_bytes > 5 * 1024 * 1024),
        ("<3min wall clock", elapsed < 180),
        ("video stream present", video_stream is not None),
        ("audio stream present", audio_stream is not None),
        (
            "video is 9:16 (1080x1920)",
            video_stream is not None
            and video_stream.get("width") == 1080
            and video_stream.get("height") == 1920,
        ),
        (
            "duration ~150s (within 5s)",
            fmt.get("duration") is not None
            and abs(float(fmt["duration"]) - 150.0) < 5.0,
        ),
    ]
    for name, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {name}")

    print(f"\n[6] For visual inspection (the convention-#7 step):")
    print(f"    MP4: {saved}")
    print(f"    PNG: {frame_path}")
    print(f"    Open both. The PNG should show artwork + lyric line; the MP4")
    print(f"    should play in VLC with audio + Ken Burns + karaoke lyrics.")

    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

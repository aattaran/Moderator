"""Step 1 verification — submit a real prompt against production comments-song.app,
poll to done, dump the full song JSON.

Intentionally simple: imports the new core/comments_song_actions.py and exercises
its three public methods end-to-end. Output is the inspectable artifact for the
Step 1 gate.

Usage:
    python scripts/verify_step1_comments_song.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Make `core.*` importable when run from anywhere.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from core.comments_song_actions import (  # noqa: E402
    AUTO_STYLE_SENTINEL,
    CommentsSongClient,
    CommentsSongError,
    style_hash,
)

PROMPT = "a chill synthwave song about a quiet midnight rainstorm in tokyo"


def _truncate(value, max_len: int = 240):
    """Make long URLs/strings inspectable without flooding stdout."""
    if isinstance(value, str) and len(value) > max_len:
        return f"{value[:max_len - 20]}... [+{len(value) - max_len + 20}c]"
    return value


def _summarize(song: dict) -> dict:
    """Return song JSON with long fields shortened, lyrics counted, timestamps preserved."""
    out = {}
    for k, v in song.items():
        if k == "lyrics" and isinstance(v, list):
            out["lyrics_lineCount"] = len(v)
            out["lyrics_sample"] = [_truncate(line) for line in v[:3]]
            continue
        if isinstance(v, str):
            out[k] = _truncate(v)
        elif isinstance(v, (dict, list)):
            out[k] = json.loads(json.dumps(v, default=str))  # shallow safe copy
        else:
            out[k] = v
    return out


async def main() -> int:
    base_url = os.environ.get("COMMENTS_SONG_BASE_URL", "https://comments-song.app")
    client = CommentsSongClient(base_url=base_url)

    # 1. styleHash sanity check
    auto_hash = style_hash(None)
    print(f"\n[1] style_hash(None) -> {auto_hash}")
    print(f"    style_hash('auto') -> {style_hash(AUTO_STYLE_SENTINEL)}  (must match)")

    # 2. Submit
    print(f"\n[2] POST {base_url}/api/songs")
    print(f"    body: {{'prompt': {PROMPT!r}}}")
    print("    curl equivalent:")
    print(f"      curl -X POST {base_url}/api/songs \\")
    print(f"           -H 'Content-Type: application/json' \\")
    print(f"           -d '{json.dumps({'prompt': PROMPT})}'")
    try:
        submit_resp = await client.submit_freetext(PROMPT)
    except CommentsSongError as e:
        print(f"\n    SUBMIT FAILED: {e}")
        return 1
    print(f"\n    <- {json.dumps(submit_resp, indent=6)}")

    video_id = submit_resp["videoId"]
    s_hash = auto_hash  # no style sent => AUTO

    # 3. Poll to terminal
    print(f"\n[3] Polling /api/songs/{video_id}/{s_hash}/status")
    print(f"    (timeout 600s, 5s interval; logs status transitions only)")
    try:
        song = await client.wait_for_done(video_id, s_hash, timeout_sec=600.0, poll_interval_sec=5.0)
    except CommentsSongError as e:
        print(f"\n    WAIT FAILED: {e}")
        return 1

    # 4. Dump song JSON (summarized — full output is too verbose for stdout)
    print(f"\n[4] GET /api/songs/{video_id}/{s_hash}  -> full song JSON (summarized):")
    print(json.dumps(_summarize(song), indent=2, default=str))

    # 5. Field-presence checks against the actual song JSON shape.
    print("\n[5] Field-presence checks (Step 1 gate):")
    lyrics = song.get("lyrics") or {}
    sections = lyrics.get("sections") or []
    line_count = sum(len(s.get("lines") or []) for s in sections)
    checks = [
        ("status == 'done'", song.get("status") == "done"),
        ("sourceType == 'freetext'", song.get("sourceType") == "freetext"),
        ("song.lyrics.title is non-empty string",
         isinstance(lyrics.get("title"), str) and len(lyrics["title"]) > 0),
        ("audioUrl is HMAC-signed URL",
         isinstance(song.get("audioUrl"), str) and "sig=" in song["audioUrl"]),
        ("lyrics.sections contains lines (>=1)", line_count >= 1),
        ("actualStyle has genre/mood/tempo/vocals",
         isinstance(song.get("actualStyle"), dict)
         and all(k in song["actualStyle"] for k in ("genre", "mood", "tempo", "vocals"))),
    ]
    for name, ok in checks:
        marker = "PASS" if ok else "FAIL"
        print(f"    [{marker}] {name}")

    # Observation (not assertion): artworkUrl may legitimately be null at
    # status='done' because cover-art arrives via a separate async KIE
    # callback. Step 2 (Playwright) must wait for it to materialize.
    print(f"\n[6] Observations (non-blocking):")
    print(f"    artworkUrl present: {bool(song.get('artworkUrl'))}  (null is valid; cover-art is async)")
    print(f"    cached: {submit_resp.get('cached')}  (true on re-runs of same prompt+IP)")
    print(f"    lyrics line count: {line_count}")
    print(f"    audio.r2Key: {(song.get('audio') or {}).get('r2Key')}")

    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

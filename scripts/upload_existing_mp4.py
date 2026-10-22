"""One-shot: upload a previously-recorded MP4 to YouTube using metadata
fetched from comments-song.

Use this to recover after a partial-run failure (e.g. recording succeeded
but the upload step crashed on missing deps). Avoids re-recording, which is
real-time and wasteful.

Usage:
    python scripts/upload_existing_mp4.py \\
        --mp4 data/shorts_outputs/ft_b619a68e0cc6e890_929260ad9b9ea9fe.mp4 \\
        --video-id ft_b619a68e0cc6e890 \\
        --style-hash 929260ad9b9ea9fe \\
        --prompt "a chill synthwave song about a quiet midnight rainstorm in tokyo"
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.comments_song_actions import CommentsSongClient  # noqa: E402
from scripts.run_shorts_pipeline import build_metadata  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mp4", required=True, help="Path to the recorded MP4")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--style-hash", required=True)
    parser.add_argument("--prompt", required=True, help="The original prompt for the description")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    mp4 = Path(args.mp4).resolve()
    if not mp4.exists():
        print(f"FAIL: MP4 not found at {mp4}")
        return 1
    if mp4.stat().st_size < 1_000_000:
        print(f"FAIL: MP4 suspiciously small ({mp4.stat().st_size} bytes)")
        return 1

    print(f"\n=== FETCHING SONG JSON === videoId={args.video_id} styleHash={args.style_hash}")
    client = CommentsSongClient()
    song = await client.get_song(args.video_id, args.style_hash)
    print(f"  -> lyrics.title={(song.get('lyrics') or {}).get('title')!r}")
    print(f"  -> actualStyle={song.get('actualStyle')}")

    print(f"\n=== METADATA ===")
    meta = build_metadata(song, args.prompt)
    print(f"  title:    {meta['title']}")
    print(f"  tags:     {meta['tags']}")
    print(f"  privacy:  {meta['privacy_status']}")

    from core.youtube_actions import YouTubeActions

    # Use the comments-song-dedicated credentials (separate from the
    # moderator's tiktokshopnature channel). See run_shorts_pipeline.py
    # for the same constant; duplicated here intentionally so this script
    # has zero coupling to its sibling.
    YT_CREDENTIALS_FILE = str(ROOT / "data" / "youtube_credentials_commentssong.json")
    YT_CLIENT_SECRETS_FILE = str(ROOT / "data" / "youtube_client_secrets.json")
    yt = YouTubeActions(
        client_secrets_file=YT_CLIENT_SECRETS_FILE,
        credentials_file=YT_CREDENTIALS_FILE,
    )

    # Channel-identity probe — confirm we're about to upload to the channel
    # the operator expects. Cheap belt-and-suspenders against authing the
    # wrong Google account during scripts/youtube_auth.py re-bootstraps.
    print(f"\n=== CHANNEL IDENTITY ===")
    try:
        service = yt._get_service()
        ch = service.channels().list(part="snippet", mine=True).execute()
        items = ch.get("items") or []
        if not items:
            print("  WARN: channels.list returned 0 items — token has youtube.upload "
                  "but the account has no channel?")
        else:
            sn = items[0].get("snippet") or {}
            print(f"  channelId:   {items[0].get('id')}")
            print(f"  title:       {sn.get('title')!r}")
            print(f"  customUrl:   {sn.get('customUrl')!r}")
    except Exception as e:
        print(f"  WARN: channel-identity probe failed: {e}")
        print(f"  (continuing with upload — see error logs above)")

    print(f"\n=== UPLOADING ===  {mp4} ({mp4.stat().st_size / 1024 / 1024:.2f} MB)")
    result = yt.upload_short(
        video_path=str(mp4),
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        category_id=meta["category_id"],
        privacy_status=meta["privacy_status"],
    )
    if not result:
        print("FAIL: YouTube upload returned None — see error logs above")
        return 1
    print(f"\n=== UPLOADED ===")
    print(f"  video_id: {result['video_id']}")
    print(f"  url:      {result['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

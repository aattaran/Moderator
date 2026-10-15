"""End-to-end pipeline: prompt -> comments-song -> Shorts MP4 -> YouTube.

Default flow (no flags):
    1. POP the next runnable line from data/prompts_queue.txt (atomic write-back)
    2. SUBMIT it to https://comments-song.app/api/songs (free-text)
    3. POLL until status='done' AND artworkUrl is non-null (cover-art is async,
       so status='done' alone is insufficient — Step 1 finding)
    4. RECORD the live page in headless Chromium via core.shorts_recorder
    5. UPLOAD the resulting MP4 to YouTube as a Short via core.youtube_actions
    6. Print the YouTube video URL

--dry-run: run steps 2-4 only, save MP4 to data/dry_run_outputs/, print the
proposed YouTube metadata, and skip the upload. The queue is PEEKED, not
popped, so the same prompt can be used again on the real run.

--prompt "text": skip the queue entirely. Useful for one-off testing.

This is the staff-beta MVP — no idempotency, no DB tracking, no scheduler
integration. Crash mid-run = prompt is consumed; the comments-song API's
cache-hit short-circuit makes a manual re-add cheap. Steps 4-6 will harden
this with SQLite state.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.comments_song_actions import (  # noqa: E402
    CommentsSongClient,
    CommentsSongError,
    style_hash,
)
from core.shorts_recorder import ShortsRecorderError, record_song  # noqa: E402

PROMPTS_FILE = ROOT / "data" / "prompts_queue.txt"
DRY_RUN_DIR = ROOT / "data" / "dry_run_outputs"
SHORTS_DIR = ROOT / "data" / "shorts_outputs"
ARTWORK_TIMEOUT_SEC = 120
DONE_TIMEOUT_SEC = 600
SONG_BASE_URL = "https://comments-song.app"
# Dedicated comments-song channel credentials. Auth via
# scripts/auth_youtube_commentssong.py. Kept distinct from
# data/youtube_credentials.json (moderator's tiktokshopnature channel)
# so the two pipelines can never cross-upload.
YT_CREDENTIALS_FILE = str(ROOT / "data" / "youtube_credentials_commentssong.json")
YT_CLIENT_SECRETS_FILE = str(ROOT / "data" / "youtube_client_secrets.json")


# ─── queue handling ──────────────────────────────────────────────────────────

def _runnable_indices(lines: list[str]) -> list[int]:
    """Return the line indices that are non-empty and not comment-prefixed."""
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(i)
    return out


def peek_next_prompt(queue_path: Path) -> tuple[str | None, int]:
    """Return (first runnable prompt, count of remaining runnable). Does NOT mutate."""
    if not queue_path.exists():
        return (None, 0)
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    idxs = _runnable_indices(lines)
    if not idxs:
        return (None, 0)
    return (lines[idxs[0]].strip(), len(idxs))


def pop_next_prompt(queue_path: Path) -> tuple[str | None, int]:
    """Atomically pop the first runnable prompt. Returns (popped, remaining_count).

    Atomicity: the new file is written to <queue>.tmp and then os.replace'd over
    the original. On Windows os.replace is atomic when source and target are on
    the same filesystem (they are — same dir).
    """
    if not queue_path.exists():
        return (None, 0)
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    idxs = _runnable_indices(lines)
    if not idxs:
        return (None, 0)
    pop_at = idxs[0]
    popped = lines[pop_at].strip()
    new_lines = lines[:pop_at] + lines[pop_at + 1:]
    body = "\n".join(new_lines)
    if new_lines:
        body += "\n"
    tmp = queue_path.with_name(queue_path.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, queue_path)
    return (popped, len(idxs) - 1)


# ─── pipeline phases ─────────────────────────────────────────────────────────

def _phase(label: str, msg: str = "") -> None:
    """Print a clearly-marked phase banner so progress is scannable in stdout."""
    print(f"\n=== {label} ===" + (f" {msg}" if msg else ""), flush=True)


async def _wait_for_artwork(
    client: CommentsSongClient,
    video_id: str,
    s_hash: str,
    song: dict,
    timeout_sec: float = ARTWORK_TIMEOUT_SEC,
    poll_interval_sec: float = 5.0,
) -> dict:
    """Re-fetch get_song until artworkUrl is non-null.

    Cover-art arrives via a separate KIE callback after the audio status flips
    to 'done', so wait_for_done() returning isn't sufficient — see Step 1
    finding and shorts fixes 03c4bc1 / 0a41c4d / 08e42a1.
    """
    if song.get("artworkUrl"):
        return song
    start = time.time()
    last_log = 0.0
    while time.time() - start < timeout_sec:
        await asyncio.sleep(poll_interval_sec)
        song = await client.get_song(video_id, s_hash)
        if song.get("artworkUrl"):
            return song
        elapsed = time.time() - start
        if elapsed - last_log > 20:
            logging.info("artwork not ready yet (elapsed=%ds)", int(elapsed))
            last_log = elapsed
    raise RuntimeError(
        f"comments-song: artworkUrl did not arrive within {timeout_sec}s for "
        f"{video_id}/{s_hash}"
    )


def build_metadata(song: dict, prompt: str) -> dict:
    """Build YouTube upload metadata.

    Title:       <song.lyrics.title> | <YYYY-MM-DD>   (date suffix prevents
                 YouTube duplicate-title penalty per planning Q6)
    Description: prompt + first 4 lyric lines + footer
    Tags:        ['shorts', 'ai music', 'ai generated', genre, mood]
    Category:    10 (Music)  — overrides upload_short's default 22
    Privacy:     'public'
    """
    lyrics = song.get("lyrics") or {}
    title_base = lyrics.get("title") or "Comments Song"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"{title_base} | {today}"
    if len(title) > 100:
        title = title[:100]

    flat_lines: list[str] = []
    for sec in lyrics.get("sections") or []:
        for ln in sec.get("lines") or []:
            text = ln.get("text")
            if text:
                flat_lines.append(text)
            if len(flat_lines) >= 4:
                break
        if len(flat_lines) >= 4:
            break
    first_four = "\n".join(flat_lines) if flat_lines else "(no lyrics available)"

    description = (
        f"A song generated from the prompt:\n"
        f"\"{prompt}\"\n\n"
        f"Lyrics:\n{first_four}\n\n"
        f"Made with comments-song.app\n\n"
        f"#shorts #aimusic #aigenerated"
    )

    style = song.get("actualStyle") or {}
    tags = ["shorts", "ai music", "ai generated"]
    if style.get("genre"):
        tags.append(style["genre"])
    if style.get("mood"):
        tags.append(style["mood"])

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "category_id": "10",
        "privacy_status": "public",
    }


def _print_metadata(meta: dict) -> None:
    print(f"  title:        {meta['title']}")
    print(f"  category_id:  {meta['category_id']}  (Music)")
    print(f"  privacy:      {meta['privacy_status']}")
    print(f"  tags:         {meta['tags']}")
    print(f"  description:")
    for ln in meta["description"].split("\n"):
        print(f"    {ln}")


async def run_pipeline(prompt: str, dry_run: bool) -> int:
    client = CommentsSongClient()
    s_hash = style_hash(None)  # AUTO mode — let the LLM pick genre/mood/tempo/vocals

    # 1. SUBMIT
    _phase("SUBMIT", f"prompt={prompt!r}")
    try:
        submit_resp = await client.submit_freetext(prompt)
    except CommentsSongError as e:
        print(f"FAIL: submit failed — {e}")
        return 1
    video_id = submit_resp["videoId"]
    print(
        f"  -> videoId={video_id} status={submit_resp.get('status')} "
        f"cached={submit_resp.get('cached')}"
    )

    # 2. POLLING — status='done' AND artworkUrl populated
    _phase("POLLING", f"{video_id}/{s_hash}")
    try:
        if submit_resp.get("cached") and submit_resp.get("status") == "done":
            song = await client.get_song(video_id, s_hash)
        else:
            song = await client.wait_for_done(
                video_id, s_hash, timeout_sec=DONE_TIMEOUT_SEC
            )
    except CommentsSongError as e:
        print(f"FAIL: polling failed — {e}")
        return 1
    print(
        f"  -> status=done lyrics.title="
        f"{(song.get('lyrics') or {}).get('title')!r}"
    )
    if not song.get("artworkUrl"):
        print("  -> artworkUrl is null; waiting for cover-art callback...")
        try:
            song = await _wait_for_artwork(client, video_id, s_hash, song)
        except RuntimeError as e:
            print(f"FAIL: artwork timeout — {e}")
            return 1
    print(f"  -> artworkUrl ready")

    # 3. RECORDING
    out_dir = DRY_RUN_DIR if dry_run else SHORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = out_dir / f"{video_id}_{s_hash}.mp4"
    song_url = f"{SONG_BASE_URL}/v/{video_id}/{s_hash}"
    _phase("RECORDING", f"{song_url}")
    print(f"  -> output: {mp4_path}")
    print(f"  -> recording is real-time; expect ~{song.get('durationSeconds', '?')}s + ~5s overhead")
    try:
        saved = await record_song(song_url, mp4_path)
    except ShortsRecorderError as e:
        print(f"FAIL: recording failed — {type(e).__name__}: {e}")
        return 1
    size_mb = saved.stat().st_size / (1024 * 1024)

    _phase("RECORDED", f"{saved} ({size_mb:.2f} MB)")

    # 4. METADATA
    meta = build_metadata(song, prompt)

    # 5. UPLOAD or DRY RUN
    if dry_run:
        _phase("DRY RUN", "proposed YouTube metadata (NOT uploaded)")
        _print_metadata(meta)
        print(
            f"\nDRY RUN — would have uploaded {saved.name!r} as "
            f"{meta['title']!r} to the YouTube channel authenticated by "
            f"data/youtube_credentials.json"
        )
        print(f"\nMP4 saved at: {saved}")
        return 0

    # Lazy import — keeps dry-run from failing on missing OAuth files when the
    # operator just wants to inspect output without YouTube credentials present.
    _phase("UPLOADING")
    from core.youtube_actions import YouTubeActions  # noqa: E402

    yt = YouTubeActions(
        client_secrets_file=YT_CLIENT_SECRETS_FILE,
        credentials_file=YT_CREDENTIALS_FILE,
    )
    result = yt.upload_short(
        video_path=str(saved),
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        category_id=meta["category_id"],
        privacy_status=meta["privacy_status"],
    )
    if not result:
        print("FAIL: YouTube upload returned None — see error logs above")
        return 1
    _phase("UPLOADED", result["url"])
    print(f"  video_id: {result['video_id']}")
    print(f"  url:      {result['url']}")
    return 0


# ─── entrypoint ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pop a prompt -> comments-song -> Shorts MP4 -> YouTube. "
            "Default mode pops from data/prompts_queue.txt and uploads. "
            "Pass --dry-run for a no-upload rehearsal."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Run submit + poll + record but skip the YouTube upload. "
            "MP4 lands in data/dry_run_outputs/. Queue is PEEKED, not popped."
        ),
    )
    parser.add_argument(
        "--prompt",
        help=(
            "Use this literal prompt instead of pulling from the queue. "
            "Queue is not touched."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.prompt:
        prompt = args.prompt
        print(f"Using --prompt override (queue not touched): {prompt!r}")
    elif args.dry_run:
        prompt, remaining = peek_next_prompt(PROMPTS_FILE)
        if prompt is None:
            print(
                f"FAIL: no runnable prompts in {PROMPTS_FILE}. Add prompts "
                f"(one per line, # for comments) or pass --prompt 'text'."
            )
            return 1
        print(
            f"Peeked queue (dry-run does not pop): {prompt!r} — "
            f"{remaining} runnable line(s) currently in queue"
        )
    else:
        popped, remaining = pop_next_prompt(PROMPTS_FILE)
        if popped is None:
            print(
                f"FAIL: no runnable prompts in {PROMPTS_FILE}. Add prompts "
                f"or pass --prompt 'text'."
            )
            return 1
        prompt = popped
        print(
            f"Popped from queue: {prompt!r} — {remaining} runnable line(s) "
            f"remaining after pop"
        )

    return asyncio.run(run_pipeline(prompt, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())

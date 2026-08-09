"""Whitelist-rooted enumeration of reference assets.

All actor/scene lookups go through here. Opaque ids are resolved against a fixed
root with is_relative_to() guards so the UI can never read files outside these
directories.
"""

import hashlib
import logging
import re
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Decompression-bomb cap — reference photos are curated but defense-in-depth.
Image.MAX_IMAGE_PIXELS = 50_000_000

ACTORS_ROOT = (Path("strategies") / "references" / "actors").resolve()
SCENES_ROOT = (Path("strategies") / "references" / "scenes").resolve()
THUMB_CACHE_DIR = (Path("ui") / "static" / "_thumbs").resolve()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
THUMB_SIZE = (256, 256)
_ID_RE = re.compile(r"^[A-Za-z0-9._\- ]+$")


class InvalidAssetId(ValueError):
    """Raised when a request id fails the whitelist check."""


def _validate_id(raw: str) -> str:
    """Reject ids containing path separators, traversal tokens, or control chars."""
    if not raw or len(raw) > 128:
        raise InvalidAssetId("empty or too long")
    if any(c in raw for c in ("/", "\\", "\0", "..")):
        raise InvalidAssetId("forbidden character")
    if not _ID_RE.match(raw):
        raise InvalidAssetId("non-ascii or unsafe character")
    return raw


def _resolve_under(root: Path, raw_id: str) -> Path:
    safe = _validate_id(raw_id)
    target = (root / safe).resolve()
    if not target.is_relative_to(root):
        raise InvalidAssetId("path escape")
    if not target.exists():
        raise InvalidAssetId("not found")
    return target


def _safe_file(path: Path, root: Path) -> Path | None:
    """Resolve `path` (following symlinks) and confirm it stays under `root`.
    Returns the resolved path or None if the file escapes, doesn't exist, or isn't a regular file.
    """
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_file() or not resolved.is_relative_to(root):
        return None
    return resolved


def _first_image(folder: Path, root: Path) -> Path | None:
    """Pick the most representative image in an actor folder (prefers 'front face').
    Every returned candidate is resolved + checked against `root` to block symlink escape.
    """
    candidates: list[Path] = []
    for p in folder.iterdir():
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        safe = _safe_file(p, root)
        if safe is not None:
            candidates.append(safe)
    if not candidates:
        return None
    frontal = [p for p in candidates if "front" in p.stem.lower() and "grid" not in p.stem.lower()]
    if frontal:
        return frontal[0]
    non_grid = [p for p in candidates if "grid" not in p.stem.lower() and "sheet" not in p.stem.lower()]
    return (non_grid or candidates)[0]


# ── Actors ───────────────────────────────────────────────────────

def list_actors() -> list[dict]:
    """Enumerate actor folders under ACTORS_ROOT. Only counts symlink-safe images."""
    if not ACTORS_ROOT.exists():
        return []
    out = []
    for d in sorted(ACTORS_ROOT.iterdir(), key=lambda p: p.name):
        if not d.is_dir():
            continue
        # Skip symlinked directories pointing outside the root
        try:
            d_resolved = d.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not d_resolved.is_relative_to(ACTORS_ROOT):
            continue
        images = [
            p for p in d.iterdir()
            if p.suffix.lower() in IMAGE_EXTS and _safe_file(p, ACTORS_ROOT) is not None
        ]
        out.append({
            "id": d.name,
            "name": d.name,
            "photo_count": len(images),
            "thumb_url": f"/api/assets/actors/{d.name}/thumb",
        })
    return out


def actor_thumb_path(raw_id: str) -> Path:
    """Return cached thumbnail path for an actor folder's representative image."""
    folder = _resolve_under(ACTORS_ROOT, raw_id)
    src = _first_image(folder, ACTORS_ROOT)
    if src is None:
        raise InvalidAssetId("no images in folder")
    return _ensure_thumb(src, cache_key=f"actor_{raw_id}")


def actor_photos(raw_id: str) -> Path:
    """Return the validated actor folder path (for passing to the generator)."""
    return _resolve_under(ACTORS_ROOT, raw_id)


# ── Scenes ───────────────────────────────────────────────────────

def list_scenes(aspect: str | None = None) -> list[dict]:
    """Enumerate scene images, optionally filtered by aspect ('9:16' or '16:9')."""
    if not SCENES_ROOT.exists():
        return []
    out = []
    # Map user-facing aspect to the substring used in filenames
    aspect_token = {"9:16": "9x16", "16:9": "16x9"}.get(aspect or "")
    for f in sorted(SCENES_ROOT.iterdir(), key=lambda p: p.name):
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS:
            continue
        if aspect_token and aspect_token not in f.name:
            continue
        out.append({
            "id": f.name,
            "name": f.stem,
            "thumb_url": f"/api/assets/scenes/{f.name}/thumb",
        })
    return out


def scene_thumb_path(raw_id: str) -> Path:
    """Return cached thumbnail path for a scene image."""
    src = _resolve_under(SCENES_ROOT, raw_id)
    return _ensure_thumb(src, cache_key=f"scene_{raw_id}")


def scene_image_path(raw_id: str) -> Path:
    """Return the validated full-size scene path (for generator input)."""
    return _resolve_under(SCENES_ROOT, raw_id)


# ── Thumbnail cache ──────────────────────────────────────────────

def _ensure_thumb(src: Path, cache_key: str) -> Path:
    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key_hash = hashlib.sha1(f"{cache_key}:{src}:{src.stat().st_mtime_ns}".encode()).hexdigest()[:16]
    dest = THUMB_CACHE_DIR / f"{key_hash}.jpg"
    if dest.exists():
        return dest
    try:
        with Image.open(src) as img:
            img.load()
            img = img.convert("RGB")
            img.thumbnail(THUMB_SIZE)
            img.save(dest, "JPEG", quality=80)
    except Image.DecompressionBombError as e:
        logger.warning("decompression bomb rejected for %s: %s", src, e)
        raise InvalidAssetId("image too large") from e
    except Exception as e:
        logger.warning("thumbnail failed for %s: %s", src, e)
        raise
    return dest

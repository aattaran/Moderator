"""UGC video pipeline — replicated from proven video-ad JS pipeline (130+ runs).

6-stage flow (direct Kling API only):
  1. Script gen (Gemini) — angle with N clip prompts + dialogue
  2. Single frame gen (Gemini) — actor photos + product photos → ONE start frame reused for all clips
     All ref images + text prompt in a single call (no multi-turn — ensures character consistency)
  3. V3 Pro video gen (Kling direct API) — image-to-video with native audio
  4. Audio extract (FFmpeg → MP3, NOT AAC)
  5. Lip sync (Kling direct API lip sync)
  6. Stitch (FFmpeg hard cuts)

Critical rules (from 130+ validated runs):
  - Actor identity from PHOTOS, not text descriptions
  - Grid-sheets → Gemini (helps matching), NOT to Kling (causes multi-face)
  - Dialogue STRIPPED from frame gen prompts (prevents caption burn-in)
  - Visual identity in prompts: "the person", "as shown in reference" — NO appearance descriptions
  - Extension prompts: motion only, pronouns only
  - Voice gender must match actor gender

Reference: strategies/references/UGC_PIPELINE_CONFIG.md
Reference JS: strategies/video-generator-kling-direct.js
"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import fal_client
import httpx
from PIL import Image

from core.kling_client import KlingClient
from media.creative_angles import generate_angle, set_gemini_key, PRODUCT_KNOWLEDGE
from media.ugc_image_generator import PRODUCT_REFS

logger = logging.getLogger(__name__)


class RunAborted(Exception):
    """Raised when a run is aborted at the preview_gate stage."""
    pass

# ── Constants ─────────────────────────────────────────────────

NEGATIVE_PROMPT = (
    "blur, distort, low quality, text overlay, watermark, subtitles, captions, "
    "text on screen, words on screen, title card, lower third, "
    "different person, face change, overexaggeration, inconsistent appearance, different identity, "
    "clothing color change, outfit change, wardrobe shift, "
    "bottle shape change, object morphing, object deformation, "
    # Anti-Kling-text-drift: V3 is documented to mutate label text + dosage numbers
    # over 5s of motion (e.g. 200 MG → 750 MG, DIHYDROBERBERINE → DEREKORINE).
    "label text mutation, fabricated text, fake dosage, changed milligrams, "
    "invented product name, scrambled letters, label morphing, text scrambling"
    "bottle covering mouth, bottle obscuring face, bottle over lips, "
    "extra hand, three hands, phantom limb, disembodied arm, "
    "holding bottle by cap only, pinching lid, unnatural grip, "
    "floating camera, suspended phone, hovering phone, phone in mid-air, "
    "camera floating, phone defying gravity, unsupported phone"
)

# Appearance details Gemini bakes into every start frame.
# Kling inherits the start frame, so details set here persist through video gen.
ACTOR_APPEARANCE_DETAILS = (
    "Natural great skin texture, made-up nice hair, clean and neat appearance, "
    "Hands are well-groomed: clean, neat nails with a subtle natural manicure, "
    "(neutral or soft nude polish, or clean bare nails — no chips, no dirt). "
    "Fingers render realistically with correct count and proportion when visible. "
    "Cuticles are tidy."
)

VIDEO_ASPECT_RATIOS = {
    "instagram": "9:16",
    "tiktok": "9:16",
    "youtube": "9:16",
    "facebook": "16:9",
    "x": "16:9",
}

PLATFORM_SHORT = {
    "instagram": "ig",
    "tiktok": "tt",
    "youtube": "yt",
    "facebook": "fb",
    "x": "x",
}

# Gemini TTS voice mapping — gender-matched
TTS_VOICES = {
    "female": "Kore",     # warm female
    "male": "Charon",     # warm male
}

# Image extensions to scan in actor/product dirs
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _get_product_for_topic(topic: str) -> dict:
    """Match content topic to the right product."""
    for product in PRODUCT_REFS.values():
        if topic in product["topics"]:
            return product
    return PRODUCT_REFS["dbh"]


def _get_product_key(topic: str) -> str:
    """Get the product key (dbh, ark, nmnh, h2) for a topic."""
    for key, product in PRODUCT_REFS.items():
        if topic in product["topics"]:
            return key
    return "dbh"


# ── Actor/Product Photo Helpers ───────────────────────────────


def _is_grid_sheet(path: Path) -> bool:
    """Detect if an image is a multi-face grid sheet.

    Grid-sheets go TO Gemini (helps matching) but NOT to Kling (causes multi-face).
    """
    name = path.stem.lower()
    if "grid" in name or "sheet" in name or "collage" in name:
        return True
    try:
        with Image.open(path) as img:
            w, h = img.size
            ratio = w / h if h > 0 else 1
            if ratio > 2.0 or ratio < 0.5:
                return True
    except Exception:
        pass
    return False


def _pixel_area(path: Path) -> int:
    """Get pixel area for sorting by size (largest first)."""
    try:
        with Image.open(path) as img:
            return img.size[0] * img.size[1]
    except Exception:
        return 0


def _filter_large_images(paths: list[Path], max_count: int = 4) -> list[Path]:
    """Sort images by pixel area (largest first), return top N."""
    return sorted(paths, key=_pixel_area, reverse=True)[:max_count]


def load_actor_photos(actor_dir: str | Path, aspect_ratio: str | None = None) -> dict:
    """Load and categorize actor reference photos.

    If `aspect_ratio` is provided AND a matching subfolder exists under actor_dir
    (e.g. `9x16/` for "9:16"), loads from that subfolder instead — lets you
    pre-curate aspect-specific actor reference shots so Gemini's start frame
    composition matches the target aspect natively.

    Convention: subfolder name = aspect with `:` replaced by `x` (lowercase).
        actors/2/9x16/   → loaded when aspect_ratio="9:16"
        actors/2/16x9/   → loaded when aspect_ratio="16:9"
        actors/2/1x1/    → loaded when aspect_ratio="1:1"

    If the aspect-specific subfolder doesn't exist (or is empty), falls back to
    loading from actor_dir root — preserves existing behavior for actors that
    don't have aspect-specific shots yet.

    Returns:
        {
            "frontal": Path | None,
            "refs": [Path],
            "all": [Path],
            "grid_sheets": [Path],
            "source_dir": Path,       # which dir was actually used
        }
    """
    actor_dir = Path(actor_dir)
    if not actor_dir.exists():
        raise FileNotFoundError(f"Actor directory not found: {actor_dir}")

    # Aspect-specific subfolder discovery
    source_dir = actor_dir
    if aspect_ratio:
        sub_name = aspect_ratio.replace(":", "x").lower()  # "9:16" → "9x16"
        sub_dir = actor_dir / sub_name
        if sub_dir.is_dir():
            sub_images = [p for p in sub_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
            if sub_images:
                source_dir = sub_dir
                logger.info("actor refs: using aspect-specific %s/ subfolder (%d images)", sub_name, len(sub_images))

    all_images = sorted([
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ])

    if not all_images:
        raise FileNotFoundError(f"No images found in: {actor_dir}")

    frontal = None
    grid_sheets = []
    single_refs = []

    for img in all_images:
        name = img.stem.lower()
        if _is_grid_sheet(img):
            grid_sheets.append(img)
        elif "front" in name or "frontal" in name:
            if frontal is None:
                frontal = img
            else:
                single_refs.append(img)
        else:
            single_refs.append(img)

    if not frontal and single_refs:
        frontal = single_refs.pop(0)

    return {
        "frontal": frontal,
        "refs": single_refs,
        "all": all_images,
        "grid_sheets": grid_sheets,
        "source_dir": source_dir,
    }


_PRODUCT_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# Filename prefixes/substrings that mark a file as NOT a clean reference shot
# (AI-generated lifestyle composites, raw camera dumps). Pattern, not a file list.
_PRODUCT_IMAGE_EXCLUDE_PREFIXES = ("Gemini_Generated_", "IMG_", "main-", "1.1")
# Regex patterns for non-front bottle views. "bottle left/right/rear/back view"
# files actually show the back/side panels of the bottle (warnings, supplement
# facts) — not alternate angles of the front label. Sending them to Gemini
# causes it to composite a hybrid label with mirrored/garbled text because it
# can't tell they're alternate faces of the SAME bottle.
import re as _re
_PRODUCT_IMAGE_EXCLUDE_PATTERNS = [
    _re.compile(r"bottle\s+(left|right|rear|back|side)\b.*view", _re.IGNORECASE),
]


def _product_priority(name: str) -> int:
    """Lower = higher priority. Prefer clean front view, then sides, then macros."""
    n = name.lower()
    if "front view" in n and "bottle" in n:
        return 0  # bottle front view (canonical)
    if n.startswith("front") or n == "main.png" or n == "2.png" or n == "1.jpg":
        return 1  # other front shots
    if "bottle" in n and "view" in n:
        return 2  # other bottle angles (left, right, rear)
    if "hero_macro" in n or "macro" in n or "label" in n:
        return 3  # label close-ups (rich text detail, less full-bottle context)
    return 9  # everything else


def load_product_photos(product_key: str) -> dict:
    """Load product reference photos from PRODUCT_REFS.

    Supports two PRODUCT_REFS schemas (no hardcoding of individual file paths):
      - images_dir: folder, auto-discovers all clean image files (preferred)
      - images: explicit list (legacy fallback for one-off cases)

    Auto-discovery rules:
      - includes png/jpg/jpeg/webp
      - excludes filename prefixes that mark non-reference files (Gemini-generated etc.)
      - sorts by reference-quality priority (front view > side > macro > other)
    """
    product = PRODUCT_REFS.get(product_key, PRODUCT_REFS["dbh"])

    candidates: list[Path] = []
    if product.get("images_dir"):
        folder = Path(product["images_dir"])
        if folder.is_dir():
            for p in folder.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in _PRODUCT_IMAGE_EXTS:
                    continue
                if any(p.name.startswith(prefix) for prefix in _PRODUCT_IMAGE_EXCLUDE_PREFIXES):
                    continue
                if any(pat.search(p.name) for pat in _PRODUCT_IMAGE_EXCLUDE_PATTERNS):
                    continue
                candidates.append(p)
            candidates.sort(key=lambda p: (_product_priority(p.name), p.name.lower()))
    else:
        # Legacy explicit list
        candidates = [Path(p) for p in product.get("images", []) if Path(p).exists()]

    return {
        "frontal": candidates[0] if candidates else None,
        "refs": candidates[1:4] if len(candidates) > 1 else [],
        "all": candidates,
    }


# ── Main Pipeline ─────────────────────────────────────────────


class UGCVideoGenerator:
    """Generate UGC videos using the proven 6-stage pipeline (direct Kling API)."""

    def __init__(
        self,
        gemini_api_key: str,
        kling_access_key: str,
        kling_secret_key: str,
        fal_api_key: str = "",
        db=None,
        output_dir: Path = Path("data/media/ugc_videos"),
        **kwargs,
    ):
        self.gemini_api_key = gemini_api_key
        set_gemini_key(gemini_api_key)
        self.kling = KlingClient(access_key=kling_access_key, secret_key=kling_secret_key)
        # fal_client reads FAL_KEY from os.environ at call time. Bridge our
        # project-named FAL_API_KEY setting over to the library's expected name.
        if fal_api_key:
            os.environ["FAL_KEY"] = fal_api_key
        self.db = db
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    async def generate(
        self,
        topic: str = "blood_sugar",
        platform: str = "instagram",
        clip_count: int = 3,
        clip_duration: int = 8,
        actor_dir: str = "",
        scene_image: str = "",
        actor_gender: str = "female",
        extend_clips: bool = False,
        style_key: str | None = None,
        concept_key: str | None = None,
        visual_hook_key: str | None = None,
        kling_model: str = "kling-v3",
        kling_mode: str = "pro",
        cfg_scale: float = 0.7,
        sound: str = "on",
        aspect_ratio_override: str | None = None,
        tts_voice: str | None = None,
        director_notes: str | None = None,
        scene_description: str | None = None,
        dry_run: bool = False,
        preview_gate: bool = False,
        on_preview_ready: Any | None = None,
        run_params_json: str | None = None,
        **kwargs,
    ) -> Path:
        """Generate a multi-clip UGC video using the proven 6-stage pipeline.

        Args:
            topic: Product topic (blood_sugar, gut_health, longevity, recovery)
            platform: Target platform for aspect ratio
            clip_count: Number of clips (3, 4, 5, or 6)
            clip_duration: Duration per clip in seconds (5, 8, or 10)
            actor_dir: Path to actor reference photos (required for best results)
            scene_image: Optional scene reference image path
            actor_gender: "male" or "female" — for TTS voice matching
            extend_clips: If True, extend each clip by ~5s after generation
            style_key / concept_key / visual_hook_key: Explicit creative angle
                overrides (None = random)
            kling_model / kling_mode / cfg_scale / sound: Kling API knobs
            aspect_ratio_override: Force a specific aspect ratio regardless of platform
            tts_voice: Override voice (reserved for future use)
            director_notes: Free-form text appended to the Gemini angle prompt
            scene_description: Optional override for the angle's setting
            dry_run: Stop after Stage 2 (preview only)
            preview_gate: Pause after Stage 2 and await ``on_preview_ready`` callback
            on_preview_ready: ``async def (angle, frame_path) -> bool``. If False,
                raises RunAborted.
            run_params_json: Serialized request snapshot (for UI re-run feature)

        Returns: Path to final.mp4 (or run_dir for dry_run)
        """
        product_key = _get_product_key(topic)
        plat_short = PLATFORM_SHORT.get(platform, platform[:2])
        job_id = f"{product_key}_{plat_short}_{uuid4().hex[:6]}"
        aspect_ratio = aspect_ratio_override or VIDEO_ASPECT_RATIOS.get(platform, "9:16")

        # Create date-nested run directory — uses a temp name up front, renamed
        # after Stage 1 once we know the resolved style/concept/hook slugs.
        today = datetime.now().strftime("%Y-%m-%d")
        date_dir = self.output_dir / today
        date_dir.mkdir(parents=True, exist_ok=True)

        def _slug(s: str) -> str:
            return (s or "random").lower().replace("_", "-")

        resolution_label = "720p" if kling_mode == "std" else "1080p"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Use explicit keys if provided, else placeholder "random" — renamed after Stage 1
        initial_style_slug = _slug(style_key) if style_key and style_key != "random" else "random"
        initial_concept_slug = _slug(concept_key) if concept_key and concept_key != "random" else "random"
        initial_hook_slug = _slug(visual_hook_key) if visual_hook_key and visual_hook_key != "random" else "random"

        def _build_dir_name(style_slug: str, concept_slug: str, hook_slug: str) -> str:
            return (
                f"{product_key}_{plat_short}_{style_slug}_{concept_slug}_{hook_slug}_"
                f"{clip_count}x{clip_duration}s_{resolution_label}_{timestamp}"
            )

        run_dir = date_dir / _build_dir_name(initial_style_slug, initial_concept_slug, initial_hook_slug)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Sanity: preview_gate=True without a callback is almost certainly a
        # UI wiring bug — failing closed prevents accidental Kling credit burn.
        if preview_gate and on_preview_ready is None:
            raise ValueError(
                "preview_gate=True requires on_preview_ready callback — refusing "
                "to silently bypass the gate",
            )

        # ═══ DB: insert initial job row ═══════════════════════
        if self.db is not None:
            try:
                rel_run_dir = str(run_dir.relative_to(self.output_dir.parent))
            except ValueError:
                rel_run_dir = str(run_dir)
            # Insert raises on collision — let it bubble up. A swallowed insert
            # would mean subsequent update_video_job_step() calls no-op, losing
            # the run's audit trail.
            await self.db.insert_video_job({
                "job_id": job_id,
                "topic": topic,
                "platform": platform,
                "duration": str(clip_duration),
                "status": "running",
                "run_dir": rel_run_dir,
                "run_params_json": run_params_json,
            })

        async def _db_update(**fields):
            if self.db is None:
                return
            try:
                await self.db.update_video_job_step(job_id, **fields)
            except Exception as e:
                logger.warning("[%s] DB update failed (%s): %s", job_id, fields, e)

        # Load actor photos — aspect-aware: prefers actor_dir/{aspect}/ subfolder
        # if present (e.g. actors/2/9x16/), else falls back to actor_dir root.
        actor_photos = None
        if actor_dir and Path(actor_dir).exists():
            actor_photos = load_actor_photos(actor_dir, aspect_ratio=aspect_ratio)
            logger.info("[%s] Actor: %s (frontal=%s, refs=%d, grids=%d)",
                        job_id, actor_photos.get("source_dir", actor_dir),
                        actor_photos["frontal"].name if actor_photos["frontal"] else "none",
                        len(actor_photos["refs"]),
                        len(actor_photos["grid_sheets"]))

        # Load product photos
        product_photos = load_product_photos(product_key)
        logger.info("[%s] Product: %s (%d photos)", job_id, product_key, len(product_photos["all"]))

        pipeline_steps = []

        try:
            # ═══ STAGE 1: Script Generation (Gemini) ═══════════
            logger.info("[%s] Stage 1: Generating creative angle (%d clips × %ds)...",
                        job_id, clip_count, clip_duration)
            angle = await generate_angle(
                topic=topic,
                clip_count=clip_count,
                clip_duration=clip_duration,
                actor_gender=actor_gender,
                use_placeholders=bool(actor_photos),
                style_key=style_key,
                concept_key=concept_key,
                visual_hook_key=visual_hook_key,
                director_notes=director_notes,
                scene_description=scene_description,
            )

            # Rename run_dir now that we know the resolved angle keys
            try:
                new_dir_name = _build_dir_name(
                    _slug(angle.style),
                    _slug(angle.concept),
                    _slug(angle.visual_hook),
                )
                new_run_dir = date_dir / new_dir_name
                if new_run_dir != run_dir and not new_run_dir.exists():
                    run_dir.rename(new_run_dir)
                    run_dir = new_run_dir
                    if self.db is not None:
                        try:
                            rel_run_dir = str(run_dir.relative_to(self.output_dir.parent))
                        except ValueError:
                            rel_run_dir = str(run_dir)
                        await _db_update(run_dir=rel_run_dir)
            except Exception as e:
                logger.warning("[%s] run_dir rename failed (continuing): %s", job_id, e)

            angle_json_str = angle.model_dump_json(indent=2)
            (run_dir / "angle.json").write_text(angle_json_str, encoding="utf-8")
            await _db_update(angle_json=angle_json_str)
            pipeline_steps.append("script-gemini")
            logger.info("[%s] Angle: %s × %s × %s", job_id, angle.style_name, angle.concept, angle.visual_hook)

            # ═══ STAGE 2: Frame Generation (Gemini multi-turn) ═
            logger.info("[%s] Stage 2: Generating single start frame (reused for all %d clips)...",
                        job_id, len(angle.clips))
            await _db_update(frame_status="running")
            frames = await self._generate_frames(
                angle=angle,
                actor_photos=actor_photos,
                product_photos=product_photos,
                scene_image=scene_image,
                run_dir=run_dir,
                job_id=job_id,
                aspect_ratio=aspect_ratio,
            )
            pipeline_steps.append("frames-gemini-single")
            frame_path_str = str(frames[0]) if frames else None
            await _db_update(frame_status="complete", frame_path=frame_path_str)

            # ═══ dry_run: stop after Stage 2 ═══════════════════
            if dry_run:
                logger.info("[%s] dry_run=True: stopping after Stage 2 (preview)", job_id)
                await _db_update(status="preview_complete", completed_at=datetime.now().isoformat())
                return run_dir

            # ═══ preview_gate: wait for external confirmation ══
            if preview_gate and on_preview_ready is not None:
                logger.info("[%s] preview_gate: awaiting confirmation...", job_id)
                await _db_update(status="awaiting_confirmation")
                result = await on_preview_ready(angle, frames[0] if frames else None)
                if result is False:
                    raise RunAborted(f"{job_id} aborted at preview_gate")
                await _db_update(status="running")

            # ═══ STAGE 3: Video Generation (Kling V3 Pro direct) ═
            logger.info("[%s] Stage 3: Generating %d video clips (Kling direct API)...",
                        job_id, len(angle.clips))
            await _db_update(video_status="running")
            clip_paths, cdn_urls = await self._generate_clips(
                frames=frames,
                angle=angle,
                aspect_ratio=aspect_ratio,
                extend_clips=extend_clips,
                run_dir=run_dir,
                job_id=job_id,
                kling_model=kling_model,
                kling_mode=kling_mode,
                cfg_scale=cfg_scale,
                sound=sound,
            )
            pipeline_steps.append("video-kling-v3-pro-direct")
            await _db_update(
                video_status="complete",
                video_path=",".join(str(p) for p in clip_paths),
            )

            # ═══ STAGE 4: Audio Extraction (FFmpeg → MP3) ══════
            logger.info("[%s] Stage 4: Extracting native audio...", job_id)
            for cp in clip_paths:
                self._extract_audio(cp)
            pipeline_steps.append("audio-ffmpeg")

            # ═══ STAGE 5: Lip Sync (Sync Lipsync 2.0 Pro via fal.ai) ═
            logger.info("[%s] Stage 5: Lip sync (Sync Lipsync 2.0 Pro)...", job_id)
            await _db_update(lipsync_status="running")
            synced_paths = await self._apply_lipsync(
                clip_paths=clip_paths,
                angle=angle,
                actor_gender=actor_gender,
                run_dir=run_dir,
                job_id=job_id,
                tts_voice=tts_voice,
            )
            if any(s != c for s, c in zip(synced_paths, clip_paths)):
                pipeline_steps.append("lipsync-sync2pro")
            else:
                pipeline_steps.append("lipsync-skipped")
            await _db_update(
                lipsync_status="complete",
                lipsync_path=",".join(str(p) for p in synced_paths),
            )

            # ═══ STAGE 6: Stitch (FFmpeg hard cuts) ════════════
            logger.info("[%s] Stage 6: Stitching %d clips...", job_id, len(synced_paths))
            await _db_update(assembly_status="running")
            final_path = run_dir / f"{run_dir.name}.mp4"
            self._stitch_clips([str(p) for p in synced_paths], str(final_path))
            pipeline_steps.append("stitch-ffmpeg")
            await _db_update(assembly_status="complete", final_path=str(final_path))

            # ═══ Write metadata ════════════════════════════════
            self._write_metadata(run_dir, pipeline_steps, job_id, topic, platform, angle, actor_dir, actor_gender)

            size_mb = final_path.stat().st_size / 1024 / 1024
            logger.info("[%s] COMPLETE: %s (%.1f MB)", job_id, final_path, size_mb)
            await _db_update(status="complete", completed_at=datetime.now().isoformat())
            return final_path

        except RunAborted as e:
            logger.warning("[%s] Run aborted at preview_gate: %s", job_id, e)
            await _db_update(status="aborted", error_message=str(e))
            raise
        except Exception as e:
            logger.error("[%s] Pipeline failed at stage [%s]: %s",
                         job_id, pipeline_steps[-1] if pipeline_steps else "init", e, exc_info=True)
            await _db_update(status="failed", error_message=str(e))
            raise

    # ═══════════════════════════════════════════════════════════
    # STAGE 2: Single Frame Generation (reused for all clips)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _crop_to_aspect(frame_path: Path, aspect_ratio: str, job_id: str) -> None:
        """Center-crop an image file to match a target W:H aspect ratio.

        Overwrites frame_path in place. No-op if the current ratio is already
        within 1% of target. Required because gemini-2.5-flash-image outputs
        1024x1024 regardless of prompt hints, and Kling image2video inherits
        the source frame's aspect ratio.
        """
        try:
            w_str, h_str = aspect_ratio.split(":")
            target = float(w_str) / float(h_str)
        except Exception:
            logger.warning("[%s] invalid aspect_ratio %r, skipping crop", job_id, aspect_ratio)
            return
        try:
            with Image.open(frame_path) as img:
                w, h = img.size
                current = w / h
                if abs(current - target) / target < 0.01:
                    return  # already close enough
                if current > target:
                    # too wide — crop width
                    new_w = int(round(h * target))
                    left = (w - new_w) // 2
                    box = (left, 0, left + new_w, h)
                else:
                    # too tall — crop height
                    new_h = int(round(w / target))
                    top = (h - new_h) // 2
                    box = (0, top, w, top + new_h)
                cropped = img.crop(box)
                # Preserve PNG; most Gemini outputs are PNG
                cropped.save(frame_path, "PNG")
                logger.info(
                    "[%s] cropped start frame %dx%d -> %dx%d (aspect %s)",
                    job_id, w, h, cropped.size[0], cropped.size[1], aspect_ratio,
                )
        except Exception as e:
            logger.warning("[%s] aspect crop failed: %s", job_id, e)

    async def _generate_frames(
        self,
        angle,
        actor_photos: dict | None,
        product_photos: dict,
        scene_image: str,
        run_dir: Path,
        job_id: str,
        aspect_ratio: str = "9:16",
    ) -> list[Path]:
        """Generate a SINGLE starting frame and reuse it for ALL clips (character consistency).

        Without kling_elements, each Gemini call produces a different-looking person.
        Fix: generate only 1 frame (clip 1) with actor refs, then reuse for every clip.

        Grid-sheets are included (they help Gemini match the person).
        Dialogue is STRIPPED from prompts (prevents caption burn-in).
        """
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=self.gemini_api_key)

        # Prepare reference images
        ref_parts = []

        if actor_photos:
            # Use frontal + single-portrait refs; EXCLUDE grid_sheets entirely.
            # Grid-sheets are multi-face composites — when Gemini sees one as a
            # primary actor reference, it interprets the scene as "multiple
            # people" and generates a phantom blurred second person on the
            # frame edge. (Pixel-area sort used to put the grid-sheet first.)
            actor_ordered = []
            if actor_photos.get("frontal"):
                actor_ordered.append(actor_photos["frontal"])
            for p in actor_photos.get("refs", []):
                if p not in actor_ordered:
                    actor_ordered.append(p)
            actor_for_gemini = actor_ordered[:4]
            for img_path in actor_for_gemini:
                raw = img_path.read_bytes()
                mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                ref_parts.append(genai_types.Part.from_bytes(data=raw, mime_type=mime))

        if product_photos["all"]:
            # Preserve PRODUCT_REFS order (frontal first, macro last) instead of
            # sorting by pixel area. Area-sort would promote the label macro to
            # position 1, making Gemini's "primary" product cue a label fragment
            # rather than a full bottle silhouette — observed cause of missing
            # GLUCO VANTAGE sub-brand and blurred ingredient pills in output.
            prod_ordered = []
            if product_photos.get("frontal"):
                prod_ordered.append(product_photos["frontal"])
            for p in product_photos.get("refs", []):
                if p not in prod_ordered:
                    prod_ordered.append(p)
            for p in product_photos["all"]:
                if p not in prod_ordered:
                    prod_ordered.append(p)
            prod_for_gemini = prod_ordered[:4]
            for img_path in prod_for_gemini:
                raw = img_path.read_bytes()
                mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                ref_parts.append(genai_types.Part.from_bytes(data=raw, mime_type=mime))

        if scene_image and Path(scene_image).exists():
            raw = Path(scene_image).read_bytes()
            mime = "image/jpeg" if scene_image.lower().endswith((".jpg", ".jpeg")) else "image/png"
            ref_parts.append(genai_types.Part.from_bytes(data=raw, mime_type=mime))

        # Generate ONE frame using the first clip's prompt, reuse for all clips
        first_clip = angle.clips[0]
        frame_prompt = self._strip_dialogue(first_clip.prompt)
        imperfections = ", ".join(angle.imperfections[:2])

        text_prompt = (
            f"Generate a casual photo for a UGC video.\n\n"
            f"The reference images show the person and the product. "
            f"Generate a {angle.setting} scene where the person "
            f"is {frame_prompt}\n\n"
            f"IMPORTANT: Match the person's face, body type, and outfit EXACTLY "
            f"from the reference photos. The bottle must match the reference product images.\n"
            f"This should look like a real person filmed themselves, NOT an AI-generated image. "
            f"Include natural imperfections: {imperfections}\n"
            f"APPEARANCE: {ACTOR_APPEARANCE_DETAILS}\n"
            f"Camera: medium close-up, natural indoor lighting.\n"
            f"Aspect ratio: {aspect_ratio}.\n"
            f"Style: casual tidy setting."
            f"no studio lighting, single overhead room light. "
            f"NOT a professional photo."
        )

        parts = ref_parts + [genai_types.Part.from_text(text=text_prompt)]

        frame_path = run_dir / f"frame_{first_clip.section}.png"
        saved = False

        # Try up to 2 times in case Gemini returns text-only
        for attempt in range(2):
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash-image",
                contents=[genai_types.Content(parts=parts, role="user")],
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=genai_types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size="2K",
                    ),
                ),
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    frame_path.write_bytes(part.inline_data.data)
                    saved = True
                    break

            if saved:
                break
            logger.warning("[%s] Frame gen attempt %d: no image returned, retrying...", job_id, attempt + 1)

        if not saved:
            raise RuntimeError(f"Gemini did not return an image for clip 1 ({first_clip.section})")

        # ── Enforce target aspect ratio ──────────────────────────
        # gemini-2.5-flash-image defaults to 1024x1024 regardless of text
        # prompt hints. Kling image2video inherits the source frame's ratio,
        # so a square frame → square video. Center-crop to target aspect
        # before Stage 3 to guarantee the output matches what the user picked.
        self._crop_to_aspect(frame_path, aspect_ratio, job_id)

        logger.info("[%s] Single frame generated: %s (reusing for all %d clips)",
                    job_id, frame_path.name, len(angle.clips))

        # Return the SAME frame path for every clip
        return [frame_path] * len(angle.clips)

    @staticmethod
    def _strip_dialogue(prompt: str) -> str:
        """Remove dialogue/speech content from a visual prompt (prevents caption burn-in)."""
        result = prompt
        for marker in ["dialogue:", "says:", "speaking:", "voiceover:", "script:"]:
            lower = result.lower()
            while marker in lower:
                idx = lower.index(marker)
                end = result.find("\n", idx)
                if end == -1:
                    end = result.find(".", idx)
                if end == -1:
                    end = len(result)
                result = result[:idx] + result[end:]
                lower = result.lower()
        return result.strip()

    # ═══════════════════════════════════════════════════════════
    # STAGE 3: Video Generation (Kling V3 Pro direct API)
    # ═══════════════════════════════════════════════════════════

    async def _generate_clips(
        self,
        frames: list[Path],
        angle,
        aspect_ratio: str,
        extend_clips: bool,
        run_dir: Path,
        job_id: str,
        kling_model: str = "kling-v3",
        kling_mode: str = "pro",
        cfg_scale: float = 0.5,
        sound: str = "on",
    ) -> tuple[list[Path], list[str]]:
        """Generate video clips via direct Kling API, throttled to 2 concurrent submissions.

        Submitting all clips simultaneously triggers Kling's per-minute rate limit (HTTP 429).
        A semaphore(2) allows two submissions in flight at once while keeping queue pressure low.

        Returns (clip_paths, cdn_urls) — CDN URLs needed for Kling native lip sync.
        """
        # Limit concurrent image2video submissions to avoid Kling 429 rate-limit cascades.
        sem = asyncio.Semaphore(2)

        async def _throttled_clip(frame, clip):
            async with sem:
                output_path = run_dir / f"clip_{clip.section}.mp4"
                prompt = clip.prompt
                if clip.dialogue:
                    prompt = f'{clip.prompt}\n\nThe person speaks directly to camera saying: "{clip.dialogue}"'
                return await self._generate_single_clip(
                    frame_path=frame,
                    prompt=prompt,
                    duration=clip.duration,
                    aspect_ratio=aspect_ratio,
                    output_path=output_path,
                    extend=extend_clips,
                    extension_prompt=clip.extension_prompt,
                    job_id=job_id,
                    clip_label=clip.section,
                    kling_model=kling_model,
                    kling_mode=kling_mode,
                    cfg_scale=cfg_scale,
                    sound=sound,
                )

        tasks = [_throttled_clip(frame, clip) for frame, clip in zip(frames, angle.clips)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        clip_paths = []
        cdn_urls = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("[%s] Clip %d (%s) failed: %s", job_id, i + 1, angle.clips[i].section, result)
                raise result
            path, url = result
            clip_paths.append(path)
            cdn_urls.append(url)
            logger.info("[%s] Clip %d/%d (%s): done", job_id, i + 1, len(results), angle.clips[i].section)

        return clip_paths, cdn_urls

    async def _generate_single_clip(
        self,
        frame_path: Path,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        output_path: Path,
        extend: bool,
        extension_prompt: str | None,
        job_id: str,
        clip_label: str,
        kling_model: str = "kling-v3",
        kling_mode: str = "pro",
        cfg_scale: float = 0.5,
        sound: str = "on",
    ) -> tuple[Path, str]:
        """Generate a single clip via direct Kling API. Returns (local_path, cdn_url)."""
        logger.info("[%s] Kling %s %s: %s (%ds)...", job_id, kling_model, kling_mode, clip_label, duration)

        # Phase 2b: add reference_images= here
        task_id = await self.kling.image_to_video_from_file(
            image_path=str(frame_path),
            prompt=prompt,
            model_name=kling_model,
            mode=kling_mode,
            duration=str(duration),
            aspect_ratio=aspect_ratio,
            negative_prompt=NEGATIVE_PROMPT,
            cfg_scale=cfg_scale,
            sound=sound,
        )

        result = await self.kling.poll_until_complete(task_id, poll_interval=10, timeout=600)
        video_url = result["url"]
        video_id = result["id"]

        # Optionally extend
        if extend and extension_prompt:
            try:
                ext_task_id = await self.kling.extend_video(
                    video_id=video_id,
                    prompt=extension_prompt,
                    negative_prompt=NEGATIVE_PROMPT,
                )
                ext_result = await self.kling.poll_extend(ext_task_id, poll_interval=10, timeout=600)
                video_url = ext_result["url"]
                logger.info("[%s] Extended %s to %ds", job_id, clip_label, ext_result.get("duration", 0))
            except Exception as e:
                logger.warning("[%s] Extension failed for %s (using original): %s", job_id, clip_label, e)

        await self.kling.download_video(video_url, str(output_path))
        return output_path, video_url

    # ═══════════════════════════════════════════════════════════
    # STAGE 4: Audio Extraction
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _extract_audio(clip_path: Path) -> Path | None:
        """Extract native audio as MP3 (NOT AAC — lip sync may reject AAC)."""
        audio_path = clip_path.with_suffix(".mp3")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(clip_path), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(audio_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 0:
            return audio_path
        return None

    # ═══════════════════════════════════════════════════════════
    # STAGE 5: Lip Sync (Sync Lipsync 2.0 Pro via fal.ai)
    # Proven flow from reference JS pipeline (130+ runs):
    #   1. Kling V3 Pro generates video with native audio (sound='on', dialogue in prompt)
    #   2. Extract native audio as MP3 from clip
    #   3. Feed video + its own MP3 through Sync Lipsync 2.0 Pro → precise mouth sync
    # ═══════════════════════════════════════════════════════════

    async def _apply_lipsync(
        self,
        clip_paths: list[Path],
        angle,
        actor_gender: str,
        run_dir: Path,
        job_id: str,
        tts_voice: str | None = None,
    ) -> list[Path]:
        """Apply Sync Lipsync 2.0 Pro: feed each clip + its own native audio → synced video.

        Kling V3 Pro already generates speech from dialogue in prompt (sound='on').
        Sync Lipsync re-warps the mouth to precisely match that audio.
        """
        import fal_client

        synced_paths = []
        for i, (clip_path, clip) in enumerate(zip(clip_paths, angle.clips)):
            if not clip.dialogue:
                synced_paths.append(clip_path)
                continue

            try:
                # Extract native audio as MP3 from Kling clip
                audio_path = clip_path.with_suffix(".mp3")
                if not audio_path.exists():
                    self._extract_audio(clip_path)
                if not audio_path.exists() or audio_path.stat().st_size == 0:
                    logger.warning("[%s] No audio in clip %s, skipping lip sync", job_id, clip.section)
                    synced_paths.append(clip_path)
                    continue

                # Upload video + audio to fal.ai storage
                logger.info("[%s] Sync Lipsync: uploading %s...", job_id, clip.section)
                video_url = await fal_client.upload_file_async(str(clip_path))
                audio_url = await fal_client.upload_file_async(str(audio_path))

                # Sync Lipsync 2.0 Pro — re-warp mouth to match native audio
                logger.info("[%s] Sync Lipsync 2.0 Pro: %s...", job_id, clip.section)
                result = await fal_client.subscribe_async(
                    "fal-ai/sync-lipsync/v2",
                    arguments={
                        "video_url": video_url,
                        "audio_url": audio_url,
                        "model": "lipsync-2-pro",
                        "sync_mode": "cut_off",
                        "model_mode": "lips",
                    },
                )

                synced_url = result.get("video", {}).get("url", "")
                if not synced_url:
                    logger.warning("[%s] Sync Lipsync returned no video for %s", job_id, clip.section)
                    synced_paths.append(clip_path)
                    continue

                # Download synced clip
                output_path = run_dir / f"synced_{clip.section}.mp4"
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.get(synced_url)
                    resp.raise_for_status()
                    output_path.write_bytes(resp.content)

                synced_paths.append(output_path)
                logger.info("[%s] Lip sync %s: done (Sync Lipsync 2.0 Pro)", job_id, clip.section)

            except Exception as e:
                logger.warning("[%s] Lip sync %s failed: %s", job_id, clip.section, e)
                synced_paths.append(clip_path)

        return synced_paths

    # ═══════════════════════════════════════════════════════════
    # STAGE 6: Stitch
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _stitch_clips(clip_paths: list[str], output: str):
        """Concatenate clips via FFmpeg hard cuts."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for clip in clip_paths:
                escaped = Path(clip).resolve().as_posix()
                f.write(f"file '{escaped}'\n")
            concat_file = f.name

        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                result2 = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                     "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                     "-c:a", "aac", "-b:a", "128k", output],
                    capture_output=True, text=True, timeout=300,
                )
                if result2.returncode != 0:
                    raise RuntimeError(f"FFmpeg stitch failed: {result2.stderr[:500]}")
            logger.info("Stitched %d clips → %s", len(clip_paths), Path(output).name)
        finally:
            Path(concat_file).unlink(missing_ok=True)

    # ═══════════════════════════════════════════════════════════
    # Metadata
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _write_metadata(run_dir, pipeline_steps, job_id, topic, platform, angle, actor_dir, actor_gender):
        pipeline_label = " > ".join(pipeline_steps)
        metadata = (
            f"Pipeline: {pipeline_label}\n"
            f"Job ID: {job_id}\n"
            f"Topic: {topic}\n"
            f"Product: {angle.product_name}\n"
            f"Platform: {platform}\n"
            f"Style: {angle.style_name} ({angle.style})\n"
            f"Concept: {angle.concept}\n"
            f"Visual Hook: {angle.visual_hook}\n"
            f"Actor Dir: {actor_dir or 'none (AI-generated)'}\n"
            f"Actor Gender: {actor_gender}\n"
            f"Persona: {angle.persona}\n"
            f"Setting: {angle.setting}\n"
            f"Clips: {', '.join(f'{c.section}({c.duration}s)' for c in angle.clips)}\n"
            f"Imperfections: {', '.join(angle.imperfections)}\n"
            f"\nDialogues:\n"
        )
        for c in angle.clips:
            metadata += f"  [{c.section}] {c.dialogue}\n"
        metadata += f"\nGenerated: {datetime.now().isoformat()}\n"
        (run_dir / "pipeline.txt").write_text(metadata, encoding="utf-8")

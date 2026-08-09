"""Moderator UGC UI — local-only FastAPI server.

SECURITY: This server binds to 127.0.0.1 only. Never expose over docker-compose
ports. No auth.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from config import get_settings
from media.creative_angles import ANGLE_STYLES, CONCEPTS, VISUAL_HOOKS
from media.ugc_image_generator import PRODUCT_REFS
from media.ugc_video_generator import UGCVideoGenerator
from storage.database import Database
from ui import assets as ui_assets
from ui.assets import InvalidAssetId, actor_photos, scene_image_path
from ui.costs import cost_estimate
from ui.schemas import RESOLUTION_TO_MODE, CostEstimateRequest, RunRequest

logger = logging.getLogger(__name__)

app = FastAPI(title="Moderator UGC UI")

templates = Jinja2Templates(directory="ui/templates")
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

# Output root for path-guarding frame/video file responses.
_UGC_OUTPUT_ROOT = Path("data/media/ugc_videos").resolve()


# ── SSE log bus ─────────────────────────────────────────────────


class SSEBusHandler(logging.Handler):
    """Broadcast log records to every active job queue.

    Non-blocking: drops records if any queue is full. Attached at startup to
    the two loggers the UGC pipeline writes through.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            return
        msg = msg.replace("\r", " ").replace("\n", " ")
        if len(msg) > 500:
            msg = msg[:500]
        item = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "msg": msg,
        }
        bus = getattr(app.state, "job_bus", None)
        if not bus:
            return
        for q in list(bus.values()):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass
            except Exception:
                pass


@app.on_event("startup")
async def _ui_startup() -> None:
    """Initialise run-state on app startup.

    FastAPI guarantees this runs inside the uvicorn event loop, so the lock
    binds to the right loop.
    """
    app.state.run_lock = asyncio.Lock()
    app.state.current_job_id: str | None = None
    app.state.job_bus: dict[str, asyncio.Queue] = {}
    # ui_job_id -> {"run_dir": Path|None, "final_path": Path|None, "frame_path": Path|None}
    app.state.jobs: dict[str, dict[str, Any]] = {}
    # Preview-gate state (Phase 4): generator blocks on confirm_event; abort_flag
    # tells the on_preview_ready callback whether to return True or False.
    app.state.confirm_events: dict[str, asyncio.Event] = {}
    app.state.abort_flags: dict[str, bool] = {}

    handler = SSEBusHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for name in ("media.ugc_video_generator", "core.kling_client"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        # Avoid double-attaching on reload
        if not any(isinstance(h, SSEBusHandler) for h in lg.handlers):
            lg.addHandler(handler)

    # Zombie sweep: any row still marked running/awaiting_confirmation from a
    # prior run must be a server that was killed before the generator could
    # write its terminal status. Mark them failed so the history panel is honest.
    # NOTE: uses aiosqlite directly — Database.initialize() runs executescript()
    # which breaks subsequent queries in the live server context.
    try:
        settings = get_settings()
        async with aiosqlite.connect(settings.DB_PATH) as _db:
            _db.row_factory = aiosqlite.Row
            cur = await _db.execute(
                "SELECT job_id FROM ugc_video_jobs WHERE status IN ('running','awaiting_confirmation')"
            )
            stale = await cur.fetchall()
            for row in stale:
                job_id = row["job_id"]
                try:
                    await _db.execute(
                        "UPDATE ugc_video_jobs SET status='failed', error_message=? WHERE job_id=?",
                        ("stale — server restart", job_id),
                    )
                except Exception:
                    logger.exception("zombie sweep: failed to update %s", job_id)
            await _db.commit()
        if stale:
            logger.info("zombie sweep: marked %d stale row(s) as failed", len(stale))
    except Exception:
        logger.exception("zombie sweep failed on startup")


# ── Helpers ─────────────────────────────────────────────────────


def _named_dict(mapping: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Convert a {key: {"name": ...}} mapping to [{"key": k, "name": n}, ...]."""
    out: list[dict[str, str]] = []
    for key, val in mapping.items():
        name = val.get("name") if isinstance(val, dict) else None
        out.append({"key": key, "name": name or key.replace("_", " ").title()})
    return out


# ── Root ────────────────────────────────────────────────────────


@app.get("/")
async def index(request: Request):
    """Render the form shell. Hydrated client-side via /api/options."""
    return templates.TemplateResponse(request, "index.html")


# ── Options bundle ──────────────────────────────────────────────


@app.get("/api/options")
async def get_options() -> dict[str, Any]:
    """Return all dropdown values needed by the form."""
    products = [
        {"key": key, "name": val["name"], "topics": list(val.get("topics", []))}
        for key, val in PRODUCT_REFS.items()
    ]

    return {
        "products": products,
        "styles": _named_dict(ANGLE_STYLES),
        "concepts": _named_dict(CONCEPTS),
        "visual_hooks": _named_dict(VISUAL_HOOKS),
        "platforms": ["instagram", "tiktok", "youtube", "facebook", "x"],
        "resolutions": [
            {"label": "720p", "mode": "std"},
            {"label": "1080p", "mode": "pro"},
        ],
        "aspects": ["9:16", "16:9", "1:1"],
        "clip_counts": [3, 4, 5, 6],
        "clip_durations": [5, 8, 10],
        "genders": ["female", "male"],
        "kling_models": ["kling-v3", "kling-v2-master", "kling-v1-6"],
        "poses": ["standing", "walking", "sitting"],
    }


# ── Asset listing ───────────────────────────────────────────────


@app.get("/api/assets/actors")
async def list_actors() -> list[dict]:
    return ui_assets.list_actors()


@app.get("/api/assets/scenes")
async def list_scenes(aspect: str | None = Query(default=None)) -> list[dict]:
    return ui_assets.list_scenes(aspect=aspect)


@app.get("/api/assets/actors/{actor_id}/thumb")
async def actor_thumb(actor_id: str):
    try:
        path = ui_assets.actor_thumb_path(actor_id)
    except InvalidAssetId as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/assets/scenes/{scene_id}/thumb")
async def scene_thumb(scene_id: str):
    try:
        path = ui_assets.scene_thumb_path(scene_id)
    except InvalidAssetId as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(path, media_type="image/jpeg")


# ── Cost estimate ───────────────────────────────────────────────


@app.post("/api/cost-estimate")
async def post_cost_estimate(req: CostEstimateRequest) -> dict:
    return cost_estimate(
        clip_count=req.clip_count,
        clip_duration=req.clip_duration,
        kling_mode=RESOLUTION_TO_MODE[req.resolution],
    )


# ── Runs (read-only list; create returns 501 in Phase 1) ────────


# Whitelist of allowed status filter values — keeps user input out of SQL.
# Mirrors every status string produced by the generator + preview-gate machine.
_ALLOWED_RUN_STATUSES = {
    "pending",
    "running",
    "complete",
    "failed",
    "aborted",
    "awaiting_confirmation",
    "preview_complete",
}


@app.get("/api/runs")
async def list_runs(
    product: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=32),
    since: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """List recent UGC video jobs.

    NOTE: storage/database.py has no filtered list helper today (only
    get_video_job / get_incomplete_video_jobs), so we run a parameterized
    SELECT here. Refactor into Database later if this query grows.
    """
    settings = get_settings()
    db_path = settings.DB_PATH

    where_parts: list[str] = []
    params: list[Any] = []

    if product:
        # PRODUCT_REFS is the source of truth for valid product keys.
        if product not in PRODUCT_REFS:
            raise HTTPException(status_code=400, detail="unknown product")
        # ugc_video_jobs.topic stores topic strings (e.g. blood_sugar). Map
        # the product key to its topics so the filter is meaningful.
        topics = list(PRODUCT_REFS[product].get("topics") or [])
        if not topics:
            return []
        placeholders = ",".join("?" * len(topics))
        where_parts.append(f"topic IN ({placeholders})")
        params.extend(topics)

    if status:
        if status not in _ALLOWED_RUN_STATUSES:
            raise HTTPException(status_code=400, detail="unknown status")
        where_parts.append("status = ?")
        params.append(status)

    if since:
        # Accept ISO-8601 timestamp; reject anything that doesn't parse.
        try:
            datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid since: {exc}")
        where_parts.append("started_at >= ?")
        params.append(since)

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sql = (
        f"SELECT * FROM ugc_video_jobs {where_clause} "
        f"ORDER BY started_at DESC LIMIT ?"
    )
    params.append(limit)

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("list_runs query failed")
        raise HTTPException(status_code=500, detail="database error")


@app.delete("/api/runs/{job_id}")
async def delete_run(job_id: str) -> dict:
    """Delete a UGC run row and its on-disk run directory.

    Refuses while the job is still running or awaiting preview confirmation —
    otherwise we'd rip the rug out from under an active pipeline. Run-dir
    cleanup is path-guarded against escape via `_UGC_OUTPUT_ROOT`.
    """
    settings = get_settings()
    db = Database(settings.DB_PATH)
    await db.initialize()
    row = await db.get_video_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")

    # Refuse to delete live jobs. current_job_id may be stale after a crash
    # (cleared in _run_pipeline finally block) but the status column is
    # authoritative for post-crash rows.
    if app.state.current_job_id == job_id or row.get("status") in (
        "running",
        "awaiting_confirmation",
    ):
        raise HTTPException(status_code=409, detail="cannot delete a running job")

    rel = row.get("run_dir") or ""
    if rel:
        try:
            # `run_dir` is stored relative to data/media (see
            # ugc_video_generator.py rel_run_dir computation). Join + resolve,
            # then require the result to sit under _UGC_OUTPUT_ROOT before
            # touching the filesystem.
            candidate = (Path("data/media") / rel).resolve()
            under_root = False
            try:
                under_root = candidate.is_relative_to(_UGC_OUTPUT_ROOT)
            except AttributeError:
                under_root = (
                    _UGC_OUTPUT_ROOT in candidate.parents
                    or candidate == _UGC_OUTPUT_ROOT
                )
            if under_root and candidate.exists() and candidate.is_dir():
                import shutil

                shutil.rmtree(candidate)
        except Exception:
            # Keep deleting the DB row even if disk cleanup fails — an
            # orphaned folder is recoverable, an orphaned row is not.
            logger.exception("run_dir cleanup failed for %s", job_id)

    try:
        async with aiosqlite.connect(settings.DB_PATH) as conn:
            await conn.execute(
                "DELETE FROM ugc_video_jobs WHERE job_id = ?", (job_id,)
            )
            await conn.commit()
    except Exception:
        logger.exception("failed to delete row for %s", job_id)
        raise HTTPException(status_code=500, detail="database error")

    # Drop any in-memory bookkeeping so a future identical job_id starts clean.
    app.state.jobs.pop(job_id, None)

    return {"status": "deleted", "job_id": job_id}


def _build_director_notes(req: RunRequest) -> str | None:
    """Concatenate optional director hints + user's free-text extra_prompt.

    For custom products, the product_description is injected first so
    generate_angle() can use it as the PRODUCT block via DIRECTOR NOTES.
    """
    sections: list[str] = []

    if req.product == "custom" and req.product_description:
        sections.append(f"PRODUCT DESCRIPTION:\n{req.product_description.strip()}")

    structured_parts: list[str] = []
    if req.pose:
        structured_parts.append(f"pose: {req.pose}")
    if req.bottle_closeup:
        structured_parts.append(f"bottle_closeup: {req.bottle_closeup}")
    if req.multi_shot:
        structured_parts.append("multi_shot")
    if structured_parts:
        sections.append("; ".join(structured_parts))

    extra = (req.extra_prompt or "").strip()
    if extra:
        sections.append(f"Extra instructions: {extra}")

    return "\n\n".join(sections) if sections else None


async def _run_pipeline(req: RunRequest, job_id: str) -> None:
    """Serialise pipeline execution under the run lock and drive the generator.

    The lock is acquired here (not in the handler) so the POST handler can
    return immediately with the job_id and the client can subscribe to SSE
    before the pipeline starts emitting logs.
    """
    async with app.state.run_lock:
        app.state.current_job_id = job_id
        final_path: Path | None = None
        run_dir: Path | None = None
        try:
            settings = get_settings()
            # Do NOT call db.initialize() here — executescript() in initialize()
            # leaves the connection in a broken state for subsequent queries in
            # the live server process. Migrations are already applied at startup.
            db = Database(settings.DB_PATH)
            vg = UGCVideoGenerator(
                gemini_api_key=settings.GEMINI_API_KEY,
                kling_access_key=settings.KLING_ACCESS_KEY_ID,
                kling_secret_key=settings.KLING_SECRET_KEY,
                fal_api_key=settings.FAL_API_KEY,
                db=db,
            )

            # Resolve opaque asset ids to real paths via ui.assets.
            actor_dir_path = actor_photos(req.actor_id)
            actor_dir_str = str(actor_dir_path)
            scene_image_str = ""
            if req.scene_id:
                scene_image_str = str(scene_image_path(req.scene_id))

            # Phase 4: honor req.preview_gate when not dry_run. Dry-run already
            # stops after Stage 2, so gating there would deadlock on
            # confirm_event.wait() (the generator's abort path never runs).
            use_gate = bool(req.preview_gate and not req.dry_run)
            confirm_event: asyncio.Event | None = None
            if use_gate:
                confirm_event = asyncio.Event()
                app.state.confirm_events[job_id] = confirm_event
                app.state.abort_flags[job_id] = False

                async def _on_preview_ready(angle, frame_path):
                    """Emit preview_ready SSE event and block until confirm/abort."""
                    # Record the frame path so /api/runs/{job_id}/frame resolves
                    # while the generator is paused inside this callback. Without
                    # this, the endpoint 404s because app.state.jobs[job_id] is
                    # only populated after vg.generate() returns.
                    if frame_path is not None:
                        try:
                            meta = app.state.jobs.setdefault(job_id, {})
                            meta["frame_path"] = Path(frame_path).resolve()
                        except Exception:
                            logger.exception("[%s] failed to record frame_path", job_id)
                    cost = cost_estimate(
                        clip_count=req.clip_count,
                        clip_duration=req.clip_duration,
                        kling_mode=RESOLUTION_TO_MODE[req.resolution],
                    )
                    q = app.state.job_bus.get(job_id)
                    if q is not None:
                        try:
                            q.put_nowait({
                                "event": "preview_ready",
                                "ts": datetime.utcnow().isoformat(),
                                "frame_url": f"/api/runs/{job_id}/frame",
                                "angle_style": getattr(angle, "style_name", None),
                                "angle_concept": getattr(angle, "concept", None),
                                "angle_visual_hook": getattr(angle, "visual_hook", None),
                                "clip_count": req.clip_count,
                                "clip_duration": req.clip_duration,
                                "cost": cost,
                            })
                        except Exception:
                            pass
                    # Block until /confirm or /abort sets the event.
                    # 2-hour timeout: if the user closes the tab without
                    # responding, auto-abort so the lock is never held forever.
                    try:
                        await asyncio.wait_for(confirm_event.wait(), timeout=7200.0)
                    except asyncio.TimeoutError:
                        logger.warning("[%s] preview gate timed out (2h), auto-aborting", job_id)
                        return False
                    return not app.state.abort_flags.get(job_id, False)

            result_path = await vg.generate(
                topic=req.topic,
                platform=req.platform,
                clip_count=req.clip_count,
                clip_duration=req.clip_duration,
                actor_dir=actor_dir_str,
                scene_image=scene_image_str,
                actor_gender=req.actor_gender,
                style_key=req.style_key if req.style_key != "random" else None,
                concept_key=req.concept_key if req.concept_key != "random" else None,
                visual_hook_key=req.visual_hook_key if req.visual_hook_key != "random" else None,
                kling_model=req.kling_model,
                kling_mode=RESOLUTION_TO_MODE[req.resolution],
                cfg_scale=req.cfg_scale,
                sound=req.sound,
                aspect_ratio_override=req.aspect_ratio,
                tts_voice=req.tts_voice,
                scene_description=req.scene_description,
                dry_run=req.dry_run,
                preview_gate=use_gate,
                on_preview_ready=_on_preview_ready if use_gate else None,
                run_params_json=req.model_dump_json(),
                extend_clips=req.extend_clips,
                director_notes=_build_director_notes(req),
            )

            # `generate()` returns run_dir on dry_run, else final.mp4 path.
            result_path = Path(result_path) if result_path is not None else None
            if req.dry_run:
                run_dir = result_path
            else:
                final_path = result_path
                run_dir = result_path.parent if result_path is not None else None

            # Record paths so frame/video endpoints can serve them.
            meta = app.state.jobs.setdefault(job_id, {})
            if run_dir is not None:
                meta["run_dir"] = run_dir
                # Find the stage-2 frame on disk (single-frame mode writes
                # frame_<section>.png at the top of run_dir).
                try:
                    for p in run_dir.glob("frame_*.png"):
                        meta["frame_path"] = p.resolve()
                        break
                except Exception:
                    pass
            if final_path is not None:
                meta["final_path"] = final_path.resolve()
        except Exception:
            logger.exception("[%s] pipeline failed", job_id)
            try:
                settings = get_settings()
                async with aiosqlite.connect(settings.DB_PATH) as _db:
                    await _db.execute(
                        "UPDATE ugc_video_jobs SET status='failed' WHERE job_id=?", (job_id,)
                    )
                    await _db.commit()
            except Exception:
                pass
        finally:
            # Signal "done" to the SSE listener and drop the queue. If no
            # listener ever subscribed the queue is discarded here anyway.
            q = app.state.job_bus.get(job_id)
            if q is not None:
                try:
                    q.put_nowait({"event": "done", "ts": datetime.utcnow().isoformat()})
                except asyncio.QueueFull:
                    pass
            # Drop preview-gate state. Safe even if never populated.
            app.state.confirm_events.pop(job_id, None)
            app.state.abort_flags.pop(job_id, None)
            app.state.current_job_id = None


async def _mark_zombie_failed(job_id: str) -> bool:
    """If job is awaiting_confirmation but has no in-memory event, mark it failed. Returns True if zombie."""
    settings = get_settings()
    async with aiosqlite.connect(settings.DB_PATH) as _db:
        _db.row_factory = aiosqlite.Row
        cur = await _db.execute(
            "SELECT status FROM ugc_video_jobs WHERE job_id=?", (job_id,)
        )
        row = await cur.fetchone()
        if row and row["status"] == "awaiting_confirmation":
            await _db.execute(
                "UPDATE ugc_video_jobs SET status='failed', error_message=? WHERE job_id=?",
                ("stale — server restarted before confirmation; please re-run", job_id),
            )
            await _db.commit()
            return True
    return False


@app.post("/api/runs/{job_id}/confirm")
async def confirm_run(job_id: str) -> dict:
    """Resume a preview-gated run — generator proceeds to Stages 3-6."""
    event = app.state.confirm_events.get(job_id)
    if event is None:
        if await _mark_zombie_failed(job_id):
            raise HTTPException(status_code=409, detail="server was restarted before you confirmed — run marked failed, please re-run")
        raise HTTPException(status_code=400, detail="no pending preview confirmation for this job")
    if event.is_set():
        raise HTTPException(status_code=400, detail="already resolved")
    app.state.abort_flags[job_id] = False
    event.set()
    return {"status": "resumed"}


@app.post("/api/runs/{job_id}/abort")
async def abort_run(job_id: str) -> dict:
    """Abort a preview-gated run — generator raises RunAborted, no Kling spend."""
    event = app.state.confirm_events.get(job_id)
    if event is None:
        await _mark_zombie_failed(job_id)
        raise HTTPException(status_code=400, detail="no pending preview confirmation for this job")
    if event.is_set():
        raise HTTPException(status_code=400, detail="already resolved")
    app.state.abort_flags[job_id] = True
    event.set()
    return {"status": "aborted"}


@app.post("/api/runs")
async def create_run(req: RunRequest) -> dict:
    """Kick off a UGC video run. Returns `{job_id}` immediately.

    Enforces single-run concurrency via `app.state.run_lock`. The lock is
    acquired inside `_run_pipeline`; the check here is a best-effort early
    reject to surface 409 before we burn an SSE subscription slot.
    """
    if app.state.run_lock.locked():
        raise HTTPException(
            status_code=409,
            detail={"error": "run_in_progress", "current": app.state.current_job_id},
        )
    job_id = f"{req.product}_{req.platform[:2]}_{uuid.uuid4().hex[:6]}"
    app.state.job_bus[job_id] = asyncio.Queue(maxsize=1000)
    app.state.jobs[job_id] = {}
    asyncio.create_task(_run_pipeline(req, job_id))
    return {"job_id": job_id}


@app.get("/api/runs/{job_id}/events")
async def run_events(job_id: str):
    """Stream pipeline log lines over SSE until the pipeline emits `done`."""
    q = app.state.job_bus.get(job_id)
    if q is None:
        raise HTTPException(status_code=404, detail="job not found or already finalized")

    async def event_generator():
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=60.0)
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}
                continue
            if item.get("event") == "done":
                yield {"event": "done", "data": json.dumps(item)}
                app.state.job_bus.pop(job_id, None)
                break
            if item.get("event") == "preview_ready":
                yield {"event": "preview_ready", "data": json.dumps(item)}
                continue
            yield {"event": "log", "data": json.dumps(item)}

    return EventSourceResponse(event_generator())


def _guarded_path(raw: Path | str | None) -> Path | None:
    """Resolve `raw` and require it to sit under the UGC output root."""
    if raw is None:
        return None
    try:
        resolved = Path(raw).resolve()
    except Exception:
        return None
    try:
        if not resolved.is_relative_to(_UGC_OUTPUT_ROOT):
            return None
    except AttributeError:
        # Python <3.9 — we're on 3.11+ so this won't hit, belt + suspenders
        if _UGC_OUTPUT_ROOT not in resolved.parents and resolved != _UGC_OUTPUT_ROOT:
            return None
    return resolved


@app.get("/api/runs/{job_id}/frame")
async def run_frame(job_id: str):
    """Return the Stage 2 start frame as an image.

    First checks the in-memory job cache (for runs launched in this process).
    Falls back to the DB for historical rows — the history panel's Frame
    button uses this path to view past frames after a restart.
    """
    frame: Path | str | None = None
    meta = app.state.jobs.get(job_id)
    if meta:
        frame = meta.get("frame_path")

    if frame is None:
        settings = get_settings()
        async with aiosqlite.connect(settings.DB_PATH) as _db:
            _db.row_factory = aiosqlite.Row
            cur = await _db.execute(
                "SELECT frame_path FROM ugc_video_jobs WHERE job_id=?", (job_id,)
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        frame = row["frame_path"]
        if not frame:
            raise HTTPException(status_code=404, detail="frame not available")

    safe = _guarded_path(frame)
    if safe is None:
        raise HTTPException(status_code=400, detail="path escape")
    if not safe.is_file():
        raise HTTPException(status_code=404, detail="frame file missing")
    return FileResponse(safe, media_type="image/png")


@app.get("/api/runs/{job_id}/video")
async def run_video(job_id: str):
    """Return the stitched final.mp4 once the pipeline has finished.

    First checks the in-memory job cache (for runs launched in this process).
    Falls back to the DB for historical rows — the history panel's Play
    button uses this path to replay past runs after a restart.
    """
    final: Path | str | None = None
    meta = app.state.jobs.get(job_id)
    if meta:
        final = meta.get("final_path")

    if final is None:
        settings = get_settings()
        async with aiosqlite.connect(settings.DB_PATH) as _db:
            _db.row_factory = aiosqlite.Row
            cur = await _db.execute("SELECT final_path FROM ugc_video_jobs WHERE job_id = ?", (job_id,))
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        final = row["final_path"] if row else None
        if not final:
            raise HTTPException(status_code=404, detail="video not available")

    safe = _guarded_path(final)
    if safe is None:
        raise HTTPException(status_code=400, detail="path escape")
    if not safe.is_file():
        raise HTTPException(status_code=404, detail="video file missing")
    return FileResponse(safe, media_type="video/mp4")

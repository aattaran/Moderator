"""Rough UGC pipeline cost estimates.

Numbers are approximate and drift — update the constants when vendor prices change.
Shown to the user as "Est. ~$X.XX" with disclaimer copy; not used for billing.
"""

from typing import Literal

# Per-clip Kling V3 image-to-video (USD). Rough approximation per the JS reference pipeline.
KLING_V3_PER_CLIP = {
    ("pro", 5): 0.18,
    ("pro", 8): 0.28,
    ("pro", 10): 0.35,
    ("std", 5): 0.09,
    ("std", 8): 0.14,
    ("std", 10): 0.17,
}

# fal.ai Sync Lipsync 2.0 Pro — approximate flat per clip
SYNC_LIPSYNC_PER_CLIP = 0.04

# Gemini script + single frame gen — approximate flat per run
GEMINI_FLAT_PER_RUN = 0.01


def _kling_unit_cost(mode: str, duration: int) -> float:
    """Interpolate cost for arbitrary duration from known anchor points."""
    key = (mode, duration)
    if key in KLING_V3_PER_CLIP:
        return KLING_V3_PER_CLIP[key]
    known = [(d, c) for (m, d), c in KLING_V3_PER_CLIP.items() if m == mode]
    known.sort()
    if not known:
        return KLING_V3_PER_CLIP[("pro", 8)]
    if duration <= known[0][0]:
        return known[0][1]
    if duration >= known[-1][0]:
        return known[-1][1]
    for i in range(len(known) - 1):
        d0, c0 = known[i]
        d1, c1 = known[i + 1]
        if d0 <= duration <= d1:
            t = (duration - d0) / (d1 - d0)
            return c0 + t * (c1 - c0)
    return KLING_V3_PER_CLIP[("pro", 8)]


def cost_estimate(
    clip_count: int,
    clip_duration: int,
    kling_mode: Literal["std", "pro"] = "pro",
) -> dict:
    kling_unit = _kling_unit_cost(kling_mode, clip_duration)
    kling_total = kling_unit * clip_count
    sync_total = SYNC_LIPSYNC_PER_CLIP * clip_count
    gemini_total = GEMINI_FLAT_PER_RUN
    total = kling_total + sync_total + gemini_total

    breakdown = (
        f"Est. ~${total:.2f} "
        f"(Gemini ${gemini_total:.2f} + Kling ${kling_total:.2f} + fal.ai ${sync_total:.2f})"
    )
    return {
        "gemini": round(gemini_total, 2),
        "kling": round(kling_total, 2),
        "fal": round(sync_total, 2),
        "total": round(total, 2),
        "breakdown_str": breakdown,
        "disclaimer": "Estimates only — real costs vary.",
    }

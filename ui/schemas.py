"""Pydantic schemas for the UGC UI API.

All user-controlled enums use typing.Literal so pydantic rejects unknown values
before they reach the generator. The only free-text field is scene_description,
which is length-capped and sanitized at submission time.
"""

from typing import Literal

import re

from pydantic import BaseModel, Field, field_validator, model_validator

_TTS_VOICE_RE = re.compile(r"^[A-Za-z0-9._\- ]+$")

# ── Enum types (source of truth for /api/options) ───────────────

Platform = Literal["instagram", "tiktok", "youtube", "facebook", "x"]
Topic = Literal["blood_sugar", "gut_health", "longevity", "recovery", "custom"]
Product = Literal["dbh", "ark", "nmnh", "h2", "custom"]
ClipCount = int   # 1–12; Pydantic validates via Field in RunRequest
ClipDuration = int  # seconds, 1–30; Kling accepts any positive integer
Aspect = Literal["9:16", "16:9", "1:1"]
Resolution = Literal["720p", "1080p"]
Gender = Literal["female", "male"]
StyleKey = Literal[
    "relatable_rant",
    "casual_review",
    "ingredient_breakdown",
    "morning_routine",
    "skeptic_converted",
    "random",
]
ConceptKey = Literal[
    "unboxing",
    "product_demo",
    "lifestyle",
    "problem_solution",
    "direct_review",
    "random",
]
VisualHookKey = Literal[
    "dynamic_movement",
    "product_action",
    "facial_expression",
    "pattern_interrupt",
    "random",
]
KlingModel = Literal["kling-v3", "kling-v2-master", "kling-v1-6"]
KlingMode = Literal["std", "pro"]
SoundFlag = Literal["on", "off"]
Pose = Literal["standing", "walking", "sitting"]
BottleCloseup = Literal["yes", "no"]

# Map user-facing resolution label to Kling mode
RESOLUTION_TO_MODE: dict[Resolution, KlingMode] = {"720p": "std", "1080p": "pro"}


class CostEstimateRequest(BaseModel):
    clip_count: ClipCount = Field(3, ge=1, le=12)
    clip_duration: ClipDuration = Field(8, ge=1, le=30)
    resolution: Resolution = "1080p"


class RunRequest(BaseModel):
    """Full form submission for a UGC video run."""

    # Required
    product: Product
    topic: Topic
    platform: Platform
    actor_id: str = Field(..., min_length=1, max_length=128)
    actor_gender: Gender
    clip_count: ClipCount = Field(..., ge=1, le=12)
    clip_duration: ClipDuration = Field(..., ge=1, le=30)
    aspect_ratio: Aspect
    resolution: Resolution

    # Scene: exactly one of these two OR neither (all None = no scene)
    scene_id: str | None = Field(None, max_length=128)
    scene_description: str | None = Field(None, max_length=500)

    # Creative picks (None = random)
    style_key: StyleKey = "random"
    concept_key: ConceptKey = "random"
    visual_hook_key: VisualHookKey = "random"

    # Custom product free-text description (required when product == "custom")
    product_description: str | None = Field(None, max_length=2000)

    # Execution flags
    dry_run: bool = False
    preview_gate: bool = True

    # Advanced (optional, defaulted)
    kling_model: KlingModel = "kling-v3"
    cfg_scale: float = Field(0.7, ge=0.0, le=1.0)  # 0.7 = stricter start-frame adherence (combats Kling label drift)
    sound: SoundFlag = "on"
    tts_voice: str | None = Field(None, max_length=64)
    pose: Pose | None = None

    @field_validator("tts_voice")
    @classmethod
    def _clean_tts_voice(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _TTS_VOICE_RE.match(v):
            raise ValueError("tts_voice contains disallowed characters")
        return v
    bottle_closeup: BottleCloseup | None = None
    multi_shot: bool = False
    extend_clips: bool = False

    # Free-text addendum appended to the Gemini angle prompt via director_notes.
    extra_prompt: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _scene_xor(self):
        if self.scene_id and self.scene_description:
            raise ValueError("scene_id and scene_description are mutually exclusive")
        if self.scene_description:
            self.scene_description = _clean_free_text(self.scene_description, "scene_description")
        if self.extra_prompt:
            self.extra_prompt = _clean_free_text(self.extra_prompt, "extra_prompt")
        if self.product == "custom":
            self.topic = "custom"
            if not self.product_description or not self.product_description.strip():
                raise ValueError("product_description is required when product is 'custom'")
            self.product_description = _clean_free_text(self.product_description, "product_description")
        return self


def _clean_free_text(value: str, field: str) -> str:
    """Sanitize user free-text fields headed into a Gemini prompt."""
    cleaned = value.replace("\r", "").strip()
    forbidden = ("<|", "|>", "[SYSTEM]", "<system>", "```")
    if any(tok in cleaned for tok in forbidden):
        raise ValueError(f"{field} contains disallowed tokens")
    if any(ord(c) < 32 and c not in ("\n", "\t") for c in cleaned):
        raise ValueError(f"{field} contains control characters")
    return cleaned

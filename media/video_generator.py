"""Video generator using Kling v3 Pro (primary) and Kling O3 Pro (fallback) via fal.ai."""

import logging
from pathlib import Path
from uuid import uuid4

import fal_client
import httpx

from media.generator_interface import MediaGenerator

logger = logging.getLogger(__name__)

# Both models accessed via FAL_API_KEY
_KLING_V3_PRO = "fal-ai/kling-video/v3/pro/text-to-video"
_KLING_O3_PRO = "fal-ai/kling-video/o3/pro/text-to-video"


class VideoGenerator(MediaGenerator):
    """Video generator backed by Kling v3 Pro (primary) and Kling O3 Pro (fallback).

    Both models are accessed via fal.ai — requires FAL_API_KEY.
    Kling v3 Pro is tried first; O3 Pro is used if v3 Pro fails.
    """

    def __init__(self, api_key: str, output_dir: Path = Path("data/media")):
        if not api_key:
            raise ValueError("FAL_API_KEY is required for VideoGenerator.")
        import os
        os.environ["FAL_KEY"] = api_key
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_image(self, prompt: str, style: str = "default") -> Path:
        raise NotImplementedError("Use ImageGenerator for image generation.")

    async def generate_video(self, prompt: str, duration: int = 10) -> Path:
        """Generate a video using Kling v3 Pro, falling back to O3 Pro on failure.

        Args:
            prompt: Text description of the video.
            duration: Target duration in seconds (5 or 10 supported by Kling).

        Returns:
            Path to the saved MP4 file.
        """
        try:
            return await self._generate_with_model(_KLING_V3_PRO, prompt, duration)
        except Exception as exc:
            logger.warning("Kling v3 Pro failed (%s), falling back to O3 Pro", exc)
            return await self._generate_with_model(_KLING_O3_PRO, prompt, duration)

    async def _generate_with_model(self, model: str, prompt: str, duration: int) -> Path:
        """Submit a generation request and download the result."""
        # Kling accepts duration as 5 or 10 seconds — clamp to nearest valid value
        kling_duration = 10 if duration >= 8 else 5

        result = await fal_client.run_async(
            model,
            arguments={
                "prompt": prompt,
                "duration": str(kling_duration),
                "cfg_scale": 0.5,
            },
        )
        video_url: str = result["video"]["url"]

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(video_url)
            response.raise_for_status()

        path = self.output_dir / f"{uuid4().hex}.mp4"
        path.write_bytes(response.content)
        return path

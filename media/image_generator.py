"""Image generator using Gemini's native image generation."""

import base64
import logging
from pathlib import Path
from uuid import uuid4

from media.generator_interface import MediaGenerator

logger = logging.getLogger(__name__)

# Use Gemini 2.0 Flash which supports native image generation
_IMAGE_MODEL = "gemini-2.5-flash-image"


class ImageGenerator(MediaGenerator):
    """Image generator backed by Gemini native image generation.

    Requires GEMINI_API_KEY in environment or passed at init.
    """

    def __init__(self, api_key: str, output_dir: Path = Path("data/media")):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for ImageGenerator.")
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_image(self, prompt: str, style: str = "default") -> Path:
        """Generate an image via Gemini and save it to data/media/."""
        from google.genai import types as genai_types

        full_prompt = f"Generate an image: {prompt}"
        if style and style != "default":
            full_prompt += f", style: {style}"

        response = self.client.models.generate_content(
            model=_IMAGE_MODEL,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # Extract image from response parts
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_bytes = part.inline_data.data
                path = self.output_dir / f"{uuid4().hex}.png"
                path.write_bytes(image_bytes)
                logger.info("Generated image: %s (%d bytes)", path, len(image_bytes))
                return path

        raise RuntimeError("No image returned from Gemini")

    async def generate_video(self, prompt: str, duration: int = 10) -> Path:
        raise NotImplementedError("Use VideoGenerator for video generation.")

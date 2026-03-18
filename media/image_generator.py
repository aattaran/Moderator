"""Image generator — placeholder for Nano Banana Pro API integration."""

from pathlib import Path

from media.generator_interface import MediaGenerator


class ImageGenerator(MediaGenerator):
    """Placeholder image generator for Nano Banana Pro API.

    To integrate:
    1. Set NANO_BANANA_API_KEY in your .env
    2. Implement generate_image() with the Nano Banana Pro REST API
    3. Save generated images to data/media/ and return the path
    """

    async def generate_image(self, prompt: str, style: str = "default") -> Path:
        raise NotImplementedError(
            "Image generation not yet implemented. "
            "Integrate the Nano Banana Pro API in this class. "
            "See: https://www.banana.dev/docs"
        )

    async def generate_video(self, prompt: str, duration: int = 10) -> Path:
        raise NotImplementedError("Use VideoGenerator for video generation.")

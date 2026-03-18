"""Video generator — placeholder for Veo API integration."""

from pathlib import Path

from media.generator_interface import MediaGenerator


class VideoGenerator(MediaGenerator):
    """Placeholder video generator for Veo API.

    To integrate:
    1. Set VEO_API_KEY in your .env
    2. Implement generate_video() with the Veo REST API
    3. Save generated videos to data/media/ and return the path
    """

    async def generate_image(self, prompt: str, style: str = "default") -> Path:
        raise NotImplementedError("Use ImageGenerator for image generation.")

    async def generate_video(self, prompt: str, duration: int = 10) -> Path:
        raise NotImplementedError(
            "Video generation not yet implemented. "
            "Integrate the Veo API in this class."
        )

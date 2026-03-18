"""Abstract interface for media generation."""

from abc import ABC, abstractmethod
from pathlib import Path


class MediaGenerator(ABC):
    """Abstract base for image and video generators."""

    @abstractmethod
    async def generate_image(self, prompt: str, style: str = "default") -> Path:
        """Generate an image from a text prompt.

        Args:
            prompt: Description of the image to generate
            style: Visual style hint

        Returns:
            Path to the generated image file
        """

    @abstractmethod
    async def generate_video(self, prompt: str, duration: int = 10) -> Path:
        """Generate a video from a text prompt.

        Args:
            prompt: Description of the video to generate
            duration: Target duration in seconds

        Returns:
            Path to the generated video file
        """

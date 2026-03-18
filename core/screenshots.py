"""Screenshot capture, resize, and base64 encoding for Computer Use."""

import base64
import io
import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def capture_screenshot(display: str = ":1") -> bytes:
    """Capture the current screen via scrot and return raw PNG bytes."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["scrot", "--display", display, "--overwrite", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"scrot failed: {result.stderr}")
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def screenshot_to_base64(png_bytes: bytes) -> str:
    """Encode raw PNG bytes to base64 string for the API."""
    return base64.standard_b64encode(png_bytes).decode("utf-8")


def resize_screenshot(
    png_bytes: bytes, max_width: int = 1024, max_height: int = 768
) -> bytes:
    """Resize screenshot if it exceeds the specified dimensions.

    At 1024x768, the image is below the API's 1568px long-edge and
    1.15MP limits, so this is a no-op for our default display size.
    Included for future higher-res display support.
    """
    img = Image.open(io.BytesIO(png_bytes))

    if img.width <= max_width and img.height <= max_height:
        return png_bytes

    img.thumbnail((max_width, max_height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logger.debug(
        "Resized screenshot from %dx%d to %dx%d",
        img.width, img.height, max_width, max_height,
    )
    return buf.getvalue()


def capture_and_encode(display: str = ":1") -> str:
    """Capture screenshot and return base64-encoded PNG string."""
    raw = capture_screenshot(display)
    raw = resize_screenshot(raw)
    return screenshot_to_base64(raw)

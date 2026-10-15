"""Tests for ImageGenerator (Nano Banana Pro / Gemini Imagen 3)."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "media"


def _make_generator(output_dir, api_key="gemini-test-key"):
    """Create ImageGenerator with Gemini client mocked."""
    with patch("google.genai.Client"):
        from media.image_generator import ImageGenerator
        return ImageGenerator(api_key=api_key, output_dir=output_dir)


def test_init_requires_api_key(output_dir):
    from media.image_generator import ImageGenerator
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        ImageGenerator(api_key="", output_dir=output_dir)


def test_init_creates_output_dir(tmp_path):
    out = tmp_path / "does_not_exist"
    assert not out.exists()
    with patch("google.genai.Client"):
        from media.image_generator import ImageGenerator
        ImageGenerator(api_key="key", output_dir=out)
    assert out.exists()


def _make_genai_response(fake_bytes: bytes) -> MagicMock:
    """Build a mock generate_content response with one image part."""
    mock_part = MagicMock()
    mock_part.inline_data = MagicMock()
    mock_part.inline_data.mime_type = "image/png"
    mock_part.inline_data.data = fake_bytes
    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]
    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    return mock_response


@pytest.mark.asyncio
async def test_generate_image_calls_imagen3(output_dir):
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _make_genai_response(fake_bytes)

        from media.image_generator import ImageGenerator, _IMAGE_MODEL
        gen = ImageGenerator(api_key="key", output_dir=output_dir)
        path = await gen.generate_image("a sunset over the ocean")

    call_kwargs = mock_client.models.generate_content.call_args
    model_used = call_kwargs.kwargs.get("model") or call_kwargs.args[0]
    assert model_used == _IMAGE_MODEL
    assert path.suffix == ".png"
    assert path.read_bytes() == fake_bytes


@pytest.mark.asyncio
async def test_generate_image_appends_style_to_prompt(output_dir):
    fake_bytes = b"\x89PNG" + b"\x00" * 100

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _make_genai_response(fake_bytes)

        from media.image_generator import ImageGenerator
        gen = ImageGenerator(api_key="key", output_dir=output_dir)
        await gen.generate_image("a city", style="photorealistic")

    call_kwargs = mock_client.models.generate_content.call_args
    contents_used = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "photorealistic" in contents_used


@pytest.mark.asyncio
async def test_generate_image_saves_to_output_dir(output_dir):
    fake_bytes = b"\x89PNG" + b"\x00" * 100

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _make_genai_response(fake_bytes)

        from media.image_generator import ImageGenerator
        gen = ImageGenerator(api_key="key", output_dir=output_dir)
        path = await gen.generate_image("test")

    assert path.parent == output_dir
    assert path.exists()


@pytest.mark.asyncio
async def test_generate_image_default_style_no_suffix(output_dir):
    """style='default' should not append ', style: default' to the prompt."""
    fake_bytes = b"\x89PNG" + b"\x00" * 100

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _make_genai_response(fake_bytes)

        from media.image_generator import ImageGenerator
        gen = ImageGenerator(api_key="key", output_dir=output_dir)
        await gen.generate_image("a dog", style="default")

    call_kwargs = mock_client.models.generate_content.call_args
    contents_used = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "default" not in contents_used


@pytest.mark.asyncio
async def test_generate_video_raises_not_implemented(output_dir):
    with patch("google.genai.Client"):
        from media.image_generator import ImageGenerator
        gen = ImageGenerator(api_key="key", output_dir=output_dir)
    with pytest.raises(NotImplementedError):
        await gen.generate_video("a video")

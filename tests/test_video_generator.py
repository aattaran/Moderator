"""Tests for VideoGenerator (Kling v3 Pro + O3 Pro via fal.ai)."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from media.video_generator import _KLING_V3_PRO, _KLING_O3_PRO


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "media"


def make_generator(output_dir, api_key="fal-test-key"):
    from media.video_generator import VideoGenerator
    with patch("os.environ"):
        return VideoGenerator(api_key=api_key, output_dir=output_dir)


def test_init_requires_api_key(output_dir):
    from media.video_generator import VideoGenerator
    with pytest.raises(ValueError, match="FAL_API_KEY"):
        VideoGenerator(api_key="", output_dir=output_dir)


def test_init_creates_output_dir(tmp_path):
    out = tmp_path / "new_dir"
    assert not out.exists()
    make_generator(out)
    assert out.exists()


def test_init_sets_fal_env_key(output_dir):
    import os
    from media.video_generator import VideoGenerator
    VideoGenerator(api_key="my-fal-key", output_dir=output_dir)
    assert os.environ.get("FAL_KEY") == "my-fal-key"


@pytest.mark.asyncio
async def test_generate_image_raises_not_implemented(output_dir):
    gen = make_generator(output_dir)
    with pytest.raises(NotImplementedError):
        await gen.generate_image("test")


@pytest.mark.asyncio
async def test_generate_video_uses_kling_v3_pro_first(output_dir):
    gen = make_generator(output_dir)
    with patch.object(gen, "_generate_with_model", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = output_dir / "out.mp4"
        await gen.generate_video("a cat walking")
    # First call must be v3 Pro
    assert mock_gen.call_args_list[0].args[0] == _KLING_V3_PRO
    assert mock_gen.call_count == 1  # No fallback needed


@pytest.mark.asyncio
async def test_generate_video_falls_back_to_o3_pro_on_failure(output_dir):
    gen = make_generator(output_dir)
    call_count = 0

    async def side_effect(model, prompt, duration):
        nonlocal call_count
        call_count += 1
        if model == _KLING_V3_PRO:
            raise RuntimeError("v3 Pro quota exceeded")
        return output_dir / "out.mp4"

    with patch.object(gen, "_generate_with_model", side_effect=side_effect):
        result = await gen.generate_video("a dog running")

    assert call_count == 2
    assert result == output_dir / "out.mp4"


@pytest.mark.asyncio
async def test_generate_video_duration_clamped_to_10(output_dir):
    fake_mp4 = b"\x00\x00\x00\x18ftyp" + b"\x00" * 100
    gen = make_generator(output_dir)

    with (
        patch("fal_client.run_async", new_callable=AsyncMock) as mock_run,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_run.return_value = {"video": {"url": "https://example.com/v.mp4"}}
        mock_response = MagicMock(content=fake_mp4)
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await gen._generate_with_model(_KLING_V3_PRO, "a rocket", 15)

    args = mock_run.call_args
    assert args.kwargs["arguments"]["duration"] == "10"


@pytest.mark.asyncio
async def test_generate_video_duration_clamped_to_5(output_dir):
    fake_mp4 = b"\x00\x00\x00\x18ftyp" + b"\x00" * 100
    gen = make_generator(output_dir)

    with (
        patch("fal_client.run_async", new_callable=AsyncMock) as mock_run,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_run.return_value = {"video": {"url": "https://example.com/v.mp4"}}
        mock_response = MagicMock(content=fake_mp4)
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await gen._generate_with_model(_KLING_V3_PRO, "a rocket", 5)

    args = mock_run.call_args
    assert args.kwargs["arguments"]["duration"] == "5"


@pytest.mark.asyncio
async def test_generate_video_saves_mp4(output_dir):
    fake_mp4 = b"\x00\x00\x00\x18ftyp" + b"\x00" * 100
    gen = make_generator(output_dir)

    with (
        patch("fal_client.run_async", new_callable=AsyncMock) as mock_run,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_run.return_value = {"video": {"url": "https://example.com/v.mp4"}}
        mock_response = MagicMock(content=fake_mp4)
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        path = await gen._generate_with_model(_KLING_V3_PRO, "test", 10)

    assert path.suffix == ".mp4"
    assert path.parent == output_dir
    assert path.read_bytes() == fake_mp4


@pytest.mark.asyncio
async def test_generate_video_passes_correct_model_id(output_dir):
    """Verify the model string passed to fal_client.run_async matches the constant."""
    fake_mp4 = b"\x00" * 100
    gen = make_generator(output_dir)

    with (
        patch("fal_client.run_async", new_callable=AsyncMock) as mock_run,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_run.return_value = {"video": {"url": "https://example.com/v.mp4"}}
        mock_response = MagicMock(content=fake_mp4)
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await gen._generate_with_model(_KLING_O3_PRO, "test", 10)

    assert mock_run.call_args.args[0] == _KLING_O3_PRO

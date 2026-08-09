"""Video assembly: stitch clips, mix audio with ducking, output final video."""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoAssembler:
    """FFmpeg-based video post-production."""

    @staticmethod
    def stitch_clips(clip_paths: list[str], output: str) -> Path:
        """Concatenate multiple video clips into one seamless video.

        Uses FFmpeg concat demuxer for frame-accurate joining.
        """
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write concat file list
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for clip in clip_paths:
                # FFmpeg concat requires forward slashes and escaped quotes
                escaped = Path(clip).resolve().as_posix()
                f.write(f"file '{escaped}'\n")
            concat_file = f.name

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                # Fallback: re-encode if copy fails (different codecs between clips)
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    str(output_path),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    raise RuntimeError(f"FFmpeg stitch failed: {result.stderr[:500]}")

            logger.info("Stitched %d clips → %s (%d bytes)", len(clip_paths), output_path.name, output_path.stat().st_size)
            return output_path
        finally:
            Path(concat_file).unlink(missing_ok=True)

    @staticmethod
    def mix_audio(video: str, tts: str, output: str, ambient: str = "", duck_level: float = 0.2) -> Path:
        """Mix TTS voiceover with video audio, applying ducking.

        When TTS speaks, the video's native audio drops to duck_level (0.2 = 20%).
        Optionally mix in ambient background music.
        """
        output_path = Path(output)

        if ambient and Path(ambient).exists():
            # 3-way mix: video audio + TTS + ambient with ducking
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", tts,
                "-i", ambient,
                "-filter_complex", (
                    f"[0:a]volume=1[va];"
                    f"[2:a]volume=0.15[amb];"
                    f"[va][amb]amix=inputs=2:duration=first[bg];"
                    f"[bg][1:a]sidechaincompress=threshold=0.02:ratio=8:attack=50:release=500[ducked];"
                    f"[ducked][1:a]amix=inputs=2:duration=first[out]"
                ),
                "-map", "0:v", "-map", "[out]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(output_path),
            ]
        else:
            # 2-way mix: video audio + TTS with simple volume balance
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", tts,
                "-filter_complex", (
                    f"[0:a]volume={duck_level}[va];"
                    f"[va][1:a]amix=inputs=2:duration=first:dropout_transition=2[out]"
                ),
                "-map", "0:v", "-map", "[out]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            # Fallback: just overlay TTS on video without mixing
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", tts,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg audio mix failed: {result.stderr[:500]}")

        logger.info("Audio mixed → %s (%d bytes)", output_path.name, output_path.stat().st_size)
        return output_path

    @staticmethod
    def overlay_tts_on_video(video: str, tts: str, output: str) -> Path:
        """Overlay TTS audio onto video. Handles videos with or without existing audio."""
        output_path = Path(output)
        # Use -shortest so output matches the shorter of video/audio
        cmd = [
            "ffmpeg", "-y",
            "-i", video,
            "-i", tts,
            "-c:v", "copy", "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            # Fallback: re-encode video if copy fails
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", tts,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg overlay failed: {result.stderr[:500]}")
        logger.info("TTS overlaid -> %s", output_path.name)
        return output_path

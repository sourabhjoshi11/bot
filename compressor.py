import asyncio
import os
import uuid
from pathlib import Path

TEMP_DIR = "/tmp/terabox_videos"
MAX_TELEGRAM_SIZE = 49 * 1024 * 1024  # 49MB (safety margin)

os.makedirs(TEMP_DIR, exist_ok=True)

# Quality presets
PRESETS = {
    "high":   {"crf": 28, "scale": "1280:720", "label": "720p  — Best Quality"},
    "medium": {"crf": 32, "scale": "854:480",  "label": "480p  — Balanced"},
    "low":    {"crf": 36, "scale": "640:360",  "label": "360p  — Smallest Size"},
}

async def download_video(url: str, filename: str) -> str:
    """yt-dlp se video download karo"""
    output_path = f"{TEMP_DIR}/{filename}.%(ext)s"
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "-o", output_path,
        "--merge-output-format", "mp4",
        url
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise Exception(f"Download failed: {stderr.decode()}")

    # BUG 6 FIX: .part / .ytdl / .tmp files ignore karo
    for f in Path(TEMP_DIR).glob(f"{filename}.*"):
        if f.suffix not in ['.part', '.ytdl', '.tmp']:
            return str(f)

    raise Exception("Downloaded file not found")

async def compress_video(input_path: str, preset_key: str = "medium") -> str:
    """FFmpeg se video compress karo"""
    preset = PRESETS[preset_key]
    output_path = f"{TEMP_DIR}/compressed_{uuid.uuid4().hex}.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale={preset['scale']}:force_original_aspect_ratio=decrease",
        "-c:v", "libx264",
        "-crf", str(preset["crf"]),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        output_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise Exception(f"Compression failed: {stderr.decode()[-300:]}")

    return output_path

def get_file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)

def is_within_telegram_limit(path: str) -> bool:
    return os.path.getsize(path) <= MAX_TELEGRAM_SIZE

def cleanup(*paths):
    """Temp files delete karo"""
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

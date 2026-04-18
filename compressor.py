import asyncio
import os
import uuid
import requests
from pathlib import Path

TEMP_DIR = "/tmp/terabox_videos"
MAX_TELEGRAM_SIZE = 49 * 1024 * 1024  # 49MB

os.makedirs(TEMP_DIR, exist_ok=True)

# Quality presets
PRESETS = {
    "high":   {"crf": 28, "scale": "1280:720", "label": "720p  — Best Quality"},
    "medium": {"crf": 32, "scale": "854:480",  "label": "480p  — Balanced"},
    "low":    {"crf": 36, "scale": "640:360",  "label": "360p  — Smallest Size"},
}

async def download_video(url: str, filename: str) -> str:
    """Direct HTTP download (yt_dlp nahi)"""
    output_path = f"{TEMP_DIR}/{filename}.mp4"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.terabox.com/",
    }

    def _download():
        with requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                    if chunk:
                        f.write(chunk)

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _download)
    except Exception as e:
        raise Exception(f"Download failed: {e}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise Exception("Download complete nahi hua ya file empty hai.")

    return output_path


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
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

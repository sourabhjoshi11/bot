import yt_dlp
import re

def is_terabox_link(url: str) -> bool:
    pattern = r'(terabox\.com|teraboxapp\.com|1024tera\.com|4funbox\.com|terashare\.com|terasharelink\.com|terasharefile\.com|teraboxlink\.com)'
    return bool(re.search(pattern, url))

def normalize_url(url: str) -> str:
    pattern = r'(terabox\.com|teraboxapp\.com|1024tera\.com|4funbox\.com|terashare\.com|terasharelink\.com|terasharefile\.com|teraboxlink\.com)'
    return re.sub(pattern, 'teraboxapp.com', url)

def extract_video_info(url: str) -> dict:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'title': info.get('title', 'Video'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'formats': [
                {
                    'format_id': f['format_id'],
                    'ext': f.get('ext'),
                    'quality': f.get('height'),
                    'url': f.get('url'),
                    'filesize': f.get('filesize'),
                }
                for f in info.get('formats', [])
                if f.get('url') and f.get('ext') in ['mp4', 'mkv', 'webm']
            ],
            'direct_url': info.get('url'),
        }

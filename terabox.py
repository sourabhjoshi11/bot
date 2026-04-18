import os
import re
import requests
from urllib.parse import urlparse, parse_qs

def is_terabox_link(url: str) -> bool:
    pattern = r'(terabox\.com|teraboxapp\.com|1024tera\.com|4funbox\.com|nephobox\.com|freeterabox\.com|mirrobox\.com|momerybox\.com|tibibox\.com)'
    return bool(re.search(pattern, url))

def _extract_surl(url: str) -> str | None:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if 'surl' in qs:
        return qs['surl'][0]
    match = re.search(r'/s/([a-zA-Z0-9_-]+)', parsed.path)
    if match:
        return match.group(1)
    return None

def _make_session() -> requests.Session:
    """
    Cookie-authenticated session banao.
    TERABOX_COOKIE .env mein set honi chahiye:
      TERABOX_COOKIE=lang=en; ndus=XXXXXXXXXX
    """
    cookie = os.getenv("TERABOX_COOKIE", "")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.terabox.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.terabox.com",
    })

    if cookie:
        # Cookie string ko parse karke session mein daalo
        for part in cookie.split(';'):
            part = part.strip()
            if '=' in part:
                name, _, value = part.partition('=')
                session.cookies.set(name.strip(), value.strip(), domain='.terabox.com')
    
    return session


def extract_video_info(url: str) -> dict:
    session = _make_session()
    cookie_present = bool(os.getenv("TERABOX_COOKIE", ""))

    # Step 1: Redirect resolve karo
    try:
        resp = session.get(url, allow_redirects=True, timeout=15)
        final_url = resp.url
    except Exception as e:
        raise Exception(f"URL resolve nahi hua: {e}")

    surl = _extract_surl(final_url) or _extract_surl(url)
    if not surl:
        raise Exception("Terabox share key (surl) URL mein nahi mila. Sahi link bhejo.")

    # Step 2: Share info API
    # Cookie ho toh authenticated endpoint, nahi toh public
    if cookie_present:
        api_url = (
            f"https://www.terabox.com/api/shorturlinfo"
            f"?app_id=250528&shorturl={surl}&root=1"
        )
    else:
        api_url = (
            f"https://www.terabox.com/api/shorturlinfo"
            f"?app_id=250528&shorturl={surl}&root=1"
        )

    try:
        api_resp = session.get(api_url, timeout=15)
        data = api_resp.json()
    except Exception as e:
        raise Exception(f"Terabox API response nahi mila: {e}")

    errno = data.get('errno', -1)
    if errno == -6:
        raise Exception(
            "❌ Terabox login session expire ho gayi.\n"
            "Bot owner se bolo TERABOX_COOKIE update kare."
        )
    if errno != 0:
        raise Exception(f"Terabox API error ({errno}): {data.get('errmsg', 'Unknown')}")

    file_list = data.get('list', [])
    if not file_list:
        raise Exception("Is link mein koi file nahi mili.")

    # Video file dhundo
    file_info = None
    for f in file_list:
        fname = f.get('server_filename', '').lower()
        if any(fname.endswith(ext) for ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv']):
            file_info = f
            break

    if not file_info:
        fname = file_list[0].get('server_filename', 'unknown')
        raise Exception(
            f"❌ Video file nahi mili.\n"
            f"File mili: `{fname}`\n"
            f"Sirf mp4/mkv/webm/avi support hain."
        )

    fs_id = file_info.get('fs_id')
    if not fs_id:
        raise Exception("File ID nahi mili.")

    # Step 3: dlink fetch karo — cookie se high-speed link milti hai
    dl_api = (
        f"https://www.terabox.com/api/templatevariable"
        f"?app_id=250528&channel=0&clienttype=0"
        f"&fs_ids=[{fs_id}]&need_media_info=1"
        f"&need_share_abnormal_file=1&shorturl={surl}&root=1"
    )

    try:
        dl_resp = session.get(dl_api, timeout=15)
        dl_data = dl_resp.json()
    except Exception as e:
        raise Exception(f"Download link API fail: {e}")

    dlink = None
    info_list = dl_data.get('info', [])
    if info_list:
        dlink = info_list[0].get('dlink')
    if not dlink:
        dlink = file_info.get('dlink')

    if not dlink:
        raise Exception(
            "❌ Download link nahi mila.\n"
            "TERABOX_COOKIE .env mein set hai? Agar nahi hai toh cookie lagao."
        )

    return {
        'title': file_info.get('server_filename', 'Video'),
        'duration': file_info.get('duration'),
        'thumbnail': (
            file_info.get('thumbs', {}).get('url3')
            or file_info.get('thumbs', {}).get('url2')
        ),
        'size': file_info.get('size', 0),
        'formats': [],
        'direct_url': dlink,
        'fs_id': fs_id,
        'surl': surl,
    }

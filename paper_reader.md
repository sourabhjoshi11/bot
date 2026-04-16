# 📄 Paper Reader — Terabox Telegram Bot

## Project Overview
Yeh Telegram bot Terabox video links ko process karke users ko direct playable/downloadable video links deta hai.

---

## Architecture

```
User → Telegram Bot → Rate Limiter → Redis Cache → yt-dlp Extractor → Video Links
```

---

## File Structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point, webhook/polling setup |
| `bot.py` | Telegram handlers (start, link, callback) |
| `terabox.py` | yt-dlp based link extractor |
| `cache.py` | Redis caching layer |
| `rate_limiter.py` | Per-user rate limiting |
| `webhook.py` | aiohttp webhook server |
| `docker-compose.yml` | Docker deployment |
| `Dockerfile` | Container config |

---

## Key Components

### 1. Link Extraction (`terabox.py`)
- `is_terabox_link()` — URL validate karta hai regex se
- `extract_video_info()` — yt-dlp se video formats aur direct URLs nikalti hai

### 2. Redis Cache (`cache.py`)
- TTL: 1 hour
- Key: MD5 hash of URL
- Same link dobara fast serve hoti hai

### 3. Rate Limiter (`rate_limiter.py`)
- Sliding window algorithm
- Default: 5 requests / 60 seconds per user
- Redis Sorted Sets use karta hai

### 4. Webhook Server (`webhook.py`)
- aiohttp based
- `/webhook` — Telegram updates receive karta hai
- `/health` — Health check endpoint

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram Bot Token | Required |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `WEBHOOK_URL` | Production webhook URL | Optional |
| `PORT` | Server port | `8443` |

---

## Quick Start

```bash
# 1. Clone/extract project
cd terabox-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup .env
cp .env.example .env
# BOT_TOKEN fill karo

# 4. Run
python main.py
```

---

## Deployment (Docker)

```bash
docker-compose up -d
```

---

## Limitations

| Issue | Solution |
|-------|---------|
| Telegram 50MB file limit | Direct links dete hain, file send nahi karte |
| Terabox anti-bot measures | yt-dlp cookies support use karo |
| High traffic | Worker queue (Celery) add karo |

---

## Future Improvements
- [ ] Database — user history
- [ ] Admin panel
- [ ] Multiple language support
- [ ] Download queue system
- [ ] Analytics dashboard

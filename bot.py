import asyncio
import os
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from terabox import is_terabox_link, extract_video_info
from cache import CacheManager
from rate_limiter import RateLimiter
from compressor import (
    download_video, compress_video,
    get_file_size_mb, is_within_telegram_limit,
    cleanup, PRESETS
)

cache = CacheManager(os.getenv("REDIS_URL", "redis://localhost:6379"))
limiter = RateLimiter(os.getenv("REDIS_URL", "redis://localhost:6379"))

PENDING_TTL = 300  # 5 minutes

# BUG 5 FIX: pending_urls Redis mein store karo (memory leak fix)
async def set_pending(user_id: int, url: str):
    await cache.redis.setex(f"pending:{user_id}", PENDING_TTL, url)

async def get_pending(user_id: int) -> str | None:
    val = await cache.redis.get(f"pending:{user_id}")
    return val.decode() if val else None

async def del_pending(user_id: int):
    await cache.redis.delete(f"pending:{user_id}")

# ─────────────────────────────────────────
# /start
# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Terabox Video Bot*\n\n"
        "Send me your Terabox URLs! I will directly download them to Telegram.",
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# Link receive
# ─────────────────────────────────────────
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    if not is_terabox_link(url):
        await update.message.reply_text("❌ This is not a valid Terabox link.")
        return

    allowed, wait_time = await limiter.is_allowed(user_id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Please wait! Try again in {wait_time}s.\n"
            f"Limit: {limiter.MAX_REQUESTS} requests/minute."
        )
        return

    msg = await update.message.reply_text("⏳ Checking the link...")

    cached = await cache.get(url)
    info = cached
    if not cached:
        try:
            # BUG 2 FIX: get_event_loop() deprecated — get_running_loop() use karo
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, extract_video_info, url)
            await cache.set(url, info)
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")
            return

    # BUG 5 FIX: Redis mein save karo
    await set_pending(user_id, url)

    keyboard = [
        [InlineKeyboardButton(f"🗜 {PRESETS[k]['label']}", callback_data=f"compress_{k}")]
        for k in PRESETS
    ]
    keyboard.append([InlineKeyboardButton("🔗 Get Direct Link", callback_data="direct_link")])

    await msg.edit_text(
        f"✅ *{info.get('title', 'Video')}*\n"
        f"⏱ Duration: {info.get('duration', '?')}s\n\n"
        f"📥 Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# Callback handler
# ─────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Direct link only
    if data == "direct_link":
        url = await get_pending(user_id)
        if not url:
            await query.edit_message_text("❌ Link has expired, please send it again.")
            return
        info = await cache.get(url)
        if info and info.get('direct_url'):
            keyboard = [[InlineKeyboardButton("⬇️ Download", url=info['direct_url'])]]
            await query.edit_message_text(
                "🔗 *Direct Link Ready!*\n\nClick the button below to download:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Direct link not found.")
        await del_pending(user_id)
        return

    # Compress + send
    if data.startswith("compress_"):
        preset_key = data.split("_")[1]
        url = await get_pending(user_id)

        if not url:
            await query.edit_message_text("❌ Link has expired, please send it again.")
            return

        await query.edit_message_text(
            f"⬇️ Downloading the video...\n"
            f"🗜 Then it will be compressed to *{PRESETS[preset_key]['label']}*.\n\n"
            f"⏳ Please wait...",
            parse_mode='Markdown'
        )

        downloaded = None
        compressed = None

        should_clear_pending = True
        try:
            filename = uuid.uuid4().hex
            downloaded = await download_video(url, filename)
            original_size = get_file_size_mb(downloaded)

            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"✅ Downloaded ({original_size:.1f}MB)\n🗜 Compressing..."
            )

            if is_within_telegram_limit(downloaded):
                # Already under 50MB — direct send
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                    text=f"📤 Sending the video ({original_size:.1f}MB)..."
                )
                with open(downloaded, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=f,
                        caption="✅ Video — Terabox Bot"
                    )
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id
                )
            else:
                compressed = await compress_video(downloaded, preset_key)
                compressed_size = get_file_size_mb(compressed)

                # BUG 3 FIX: return hata ke proper message + pending URL rakho retry ke liye
                if not is_within_telegram_limit(compressed):
                    should_clear_pending = False
                    # Pending URL mat hata — user retry kar sake
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        text=(
                            f"⚠️ Even after compression, the size is {compressed_size:.1f}MB.\n"
                            f"Telegram size limit is 50MB.\n\n"
                            f"👇 Try a lower quality:"
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🗜 360p — Smallest Size", callback_data="compress_low")],
                            [InlineKeyboardButton("🔗 Get Direct Link", callback_data="direct_link")],
                        ])
                    )
                    cleanup(compressed)
                    return

                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                    text=(
                        f"✅ Compression complete!\n"
                        f"📦 {original_size:.1f}MB → {compressed_size:.1f}MB\n"
                        f"📤 Sending the video..."
                    )
                )
                with open(compressed, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=f,
                        caption=(
                            f"✅ *{PRESETS[preset_key]['label']}*\n"
                            f"📦 {original_size:.1f}MB → {compressed_size:.1f}MB"
                        ),
                        parse_mode='Markdown'
                    )
                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id
                )

        except Exception as e:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"❌ An error occurred:\n{str(e)[:200]}"
            )
        finally:
            cleanup(downloaded, compressed)
            if should_clear_pending:
                await del_pending(user_id)

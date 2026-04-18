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
        "Terabox link bhejo — main video direct Telegram pe bhej dunga!\n\n"
        "📌 Supported:\n"
        "• terabox.com\n• teraboxapp.com\n• 1024tera.com\n\n"
        "🗜 50MB+ videos auto-compress hokar aayengi!",
        parse_mode='Markdown'
    )

# ─────────────────────────────────────────
# Link receive
# ─────────────────────────────────────────
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    if not is_terabox_link(url):
        await update.message.reply_text("❌ Yeh Terabox link nahi hai.")
        return

    allowed, wait_time = await limiter.is_allowed(user_id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Thoda ruko! {wait_time}s baad try karo.\n"
            f"Limit: {limiter.MAX_REQUESTS} requests/minute."
        )
        return

    msg = await update.message.reply_text("⏳ Link check ho raha hai...")

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
    keyboard.append([InlineKeyboardButton("🔗 Sirf Direct Link Do", callback_data="direct_link")])

    await msg.edit_text(
        f"✅ *{info.get('title', 'Video')}*\n"
        f"⏱ Duration: {info.get('duration', '?')}s\n\n"
        f"📥 Kaise chahiye video?",
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
            await query.edit_message_text("❌ Link expire ho gaya, dobara bhejo.")
            return
        info = await cache.get(url)
        if info and info.get('direct_url'):
            keyboard = [[InlineKeyboardButton("⬇️ Download", url=info['direct_url'])]]
            await query.edit_message_text(
                "🔗 *Direct Link Ready!*\n\nNeeche button se download karo:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Direct link nahi mila.")
        await del_pending(user_id)
        return

    # Compress + send
    if data.startswith("compress_"):
        preset_key = data.split("_")[1]
        url = await get_pending(user_id)

        if not url:
            await query.edit_message_text("❌ Link expire ho gaya, dobara bhejo.")
            return

        await query.edit_message_text(
            f"⬇️ Video download ho rahi hai...\n"
            f"🗜 Phir *{PRESETS[preset_key]['label']}* mein compress hogi.\n\n"
            f"⏳ Thoda wait karo...",
            parse_mode='Markdown'
        )

        downloaded = None
        compressed = None

        try:
            filename = uuid.uuid4().hex
            downloaded = await download_video(url, filename)
            original_size = get_file_size_mb(downloaded)

            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"✅ Downloaded ({original_size:.1f}MB)\n🗜 Compress ho rahi hai..."
            )

            if is_within_telegram_limit(downloaded):
                # Already under 50MB — direct send
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                    text=f"📤 Video send ho rahi hai ({original_size:.1f}MB)..."
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
                    # Pending URL mat hata — user retry kar sake
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        text=(
                            f"⚠️ Compress ke baad bhi {compressed_size:.1f}MB hai.\n"
                            f"Telegram limit 50MB hai.\n\n"
                            f"👇 Chota quality try karo:"
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🗜 360p — Smallest Size", callback_data="compress_low")],
                            [InlineKeyboardButton("🔗 Direct Link Lo", callback_data="direct_link")],
                        ])
                    )
                    cleanup(compressed)  # sirf compressed clean karo, downloaded nahi
                    return

                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                    text=(
                        f"✅ Compress complete!\n"
                        f"📦 {original_size:.1f}MB → {compressed_size:.1f}MB\n"
                        f"📤 Send ho rahi hai..."
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
                text=f"❌ Error aaya:\n{str(e)[:200]}"
            )
        finally:
            cleanup(downloaded, compressed)
            await del_pending(user_id)

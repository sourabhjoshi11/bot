import asyncio
import os
from aiohttp import web
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from bot import start, handle_link, handle_callback
from webhook import setup_webhook

load_dotenv()

async def main():
    # BUG 7 FIX: BOT_TOKEN validation
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("❌ BOT_TOKEN .env mein set nahi hai!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_callback))

    await app.initialize()
    await app.start()

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    PORT = int(os.getenv("PORT", 8443))

    if WEBHOOK_URL:
        server, port = await setup_webhook(app, WEBHOOK_URL, PORT)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print(f"✅ Webhook mode: {WEBHOOK_URL} | Port: {port}")
        await asyncio.Event().wait()
    else:
        print("✅ Polling mode (development)")
        await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

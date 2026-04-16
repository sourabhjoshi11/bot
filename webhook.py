from aiohttp import web
from telegram import Update

async def setup_webhook(app, webhook_url: str, port: int = 8443):
    await app.bot.set_webhook(
        url=f"{webhook_url}/webhook",
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

    async def handle_update(request):
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(text="OK")

    async def health_check(request):
        return web.Response(text="Bot is running ✅")

    server = web.Application()
    server.router.add_post("/webhook", handle_update)
    server.router.add_get("/health", health_check)
    return server, port

# api/webhook.py
import asyncio
from aiohttp import web
from bot_core.bot import bot, dp
from bot_core.db import Database
from bot_core.handlers import *  # импортируем хендлеры

# Инициализация БД
db = Database()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(db.init())

# Передаём db в хендлеры (можно через глобальную переменную или dependency injection)
import bot_core.handlers
bot_core.handlers.db = db

async def handler(request):
    if request.method == "POST":
        update = await request.json()
        await dp.feed_webhook_update(bot, update)
        return web.json_response({"ok": True})
    return web.json_response({"error": "Method not allowed"}, status=405)

# ASGI-приложение для Vercel
app = web.Application()
app.router.add_post("/api/webhook", handler)

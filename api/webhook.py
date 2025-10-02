# api/webhook.py
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TELEGRAM_TOKEN, DATABASE_URL
from db import Database

# Глобальные переменные (инициализируются один раз при старте функции)
bot = None
dp = None
db = None

async def init_bot():
    """Инициализирует бота и БД"""
    global bot, dp, db
    if not bot:
        bot = Bot(token=TELEGRAM_TOKEN)
        dp = Dispatcher(storage=MemoryStorage())
        db = Database()
        await db.init()

async def handler(request):
    """Обрабатывает POST-запросы от Telegram"""
    if request.method != "POST":
        return web.Response(status=405)

    try:
        update = await request.json()
    except Exception:
        return web.Response(status=400)

    # Инициализируем бота, если ещё не сделано
    await init_bot()

    # Регистрируем хендлеры (можно сделать один раз при инициализации)
    from handlers import register_handlers
    register_handlers(dp, db, bot)

    # Обрабатываем обновление
    await dp.feed_webhook_update(bot, update)

    return web.json_response({"ok": True})

# Для Vercel: экспортируем функцию handler как app
app = handler

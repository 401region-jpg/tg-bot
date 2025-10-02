# api/webhook.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TELEGRAM_TOKEN, DATABASE_URL
from db import Database

# Глобальные переменные (инициализируются один раз)
_bot = None
_dp = None
_db = None

async def get_bot():
    global _bot, _dp, _db
    if _bot is None:
        _bot = Bot(token=TELEGRAM_TOKEN)
        _dp = Dispatcher(storage=MemoryStorage())
        _db = Database()
        await _db.init()
        from handlers import register_handlers
        register_handlers(_dp, _db, _bot)
    return _bot, _dp

def handler(request):
    """Vercel-совместимая функция"""
    import json
    
    if request.method != "POST":
        return {"statusCode": 405, "body": "Method Not Allowed"}

    try:
        update = json.loads(request.body)
    except Exception:
        return {"statusCode": 400, "body": "Invalid JSON"}

    # Запускаем асинхронную обработку
    async def process():
        bot, dp = await get_bot()
        await dp.feed_webhook_update(bot, update)

    asyncio.run(process())
    return {"statusCode": 200, "body": '{"ok":true}'}

# Экспортируем функцию для Vercel
app = handler

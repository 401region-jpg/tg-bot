# api/webhook.py
import json
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TELEGRAM_TOKEN
from db import Database

# Глобальные переменные (инициализируются один раз)
_bot = None
_dp = None
_db = None

async def _init_bot():
    global _bot, _dp, _db
    if _bot is None:
        _bot = Bot(token=TELEGRAM_TOKEN)
        _dp = Dispatcher(storage=MemoryStorage())
        _db = Database()
        await _db.init()
        from handlers import register_handlers
        register_handlers(_dp, _db, _bot)

def handler(request, context):
    """
    Vercel-совместимая serverless-функция.
    Обязательно называется `handler` и принимает (request, context).
    """
    if request.method != "POST":
        return {"statusCode": 405, "body": "Method Not Allowed"}

    try:
        update = json.loads(request.body)
    except Exception:
        return {"statusCode": 400, "body": "Invalid JSON"}

    # Запускаем асинхронную обработку
    asyncio.run(_init_bot())
    asyncio.run(_dp.feed_webhook_update(_bot, update))

    return {"statusCode": 200, "body": '{"ok":true}'}

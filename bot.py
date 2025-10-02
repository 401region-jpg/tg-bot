# bot.py
import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TELEGRAM_TOKEN, WEBHOOK_URL, DATABASE_URL

# Импорты
from db import Database
from handlers import register_handlers

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверка переменных
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не задан")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не задан")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL не задан")

logger.info("✅ Конфигурация загружена")

# Инициализация
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=storage)
db = Database()

async def on_startup(app):
    """Выполняется при запуске сервера"""
    await db.init()
    await register_handlers(dp, db, bot)
    # Устанавливаем вебхук
    await bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    """Выполняется при остановке"""
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.storage.close()
    await dp.storage.wait_closed()
    logger.info("🔌 Вебхук удалён")

async def handle_webhook(request):
    """Обрабатывает POST-запросы от Telegram"""
    if request.content_type == 'application/json':
        update = await request.json()
        await dp.feed_webhook_update(bot, update)
        return web.Response()
    return web.Response(status=403)

# Создаём aiohttp-приложение
app = web.Application()
app.router.add_post('/api/webhook', handle_webhook)  # Путь должен совпадать с WEBHOOK_URL
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# Для локального запуска (не используется на Vercel)
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

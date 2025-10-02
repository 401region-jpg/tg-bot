# bot.py
import asyncio
import logging
import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_TOKEN, PORT, ADMIN_ID
from db import Database  # ← Убедись, что импортируешь Database
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверка переменных
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не задан в .env")
if not ADMIN_ID:
    logger.warning("⚠️ ADMIN_ID не задан — админ-команды работать не будут")
logger.info("✅ Все переменные окружения загружены")

storage = MemoryStorage()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=storage)
db = Database()  # Использует SQLite по умолчанию (файл bot.db)

async def start_webserver():
    async def handler(request):
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Keepalive server started on port {PORT}")

async def periodic_tasks():
    # бэкап, очистка, метрики
    while True:
        try:
            await db.backup_snapshot()
            logger.info("✅ Бэкап выполнен")
        except Exception:
            logger.exception("❌ Ошибка бэкапа")

        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            # Используем метод из db.py для очистки
            await db.cleanup_old_users(cutoff)
            logger.info("🧹 Старые пользователи удалены")
        except Exception:
            logger.exception("❌ Ошибка очистки")

        await asyncio.sleep(60 * 60)  # раз в час

async def main():
    await db.init()
    await register_handlers(dp, db, bot)  # ← добавлен bot
    asyncio.create_task(start_webserver())
    asyncio.create_task(periodic_tasks())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

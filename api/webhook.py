from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer("Бот на Vercel работает через Webhook!")

app = FastAPI()

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}

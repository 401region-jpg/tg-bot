import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types

TOKEN = os.getenv("BOT_TOKEN")

# создаём один раз
bot = Bot(token=TOKEN)
dp = Dispatcher()

# простой хэндлер
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer("Привет! Бот работает на Vercel через Webhook.")

app = FastAPI()

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

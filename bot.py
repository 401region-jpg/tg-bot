# bot.py — минимальный, надёжный вариант для Render Background Worker
import os
import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = os.getenv("7517420285:AAEJMY567Htns_i3SbMqww5U0O_-TTjbPW8")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Моя анкета")],
        [KeyboardButton(text="Смотреть анкеты")]
    ],
    resize_keyboard=True
)

db = None  # глобальная ссылка на aiosqlite.Connection

async def init_db():
    global db
    db = await aiosqlite.connect("db.sqlite3")
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        age INTEGER,
        bio TEXT,
        step TEXT
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS likes(
        liker INTEGER,
        liked INTEGER,
        PRIMARY KEY(liker, liked)
    )
    """)
    await db.commit()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # проверяем, есть ли user
    async with db.execute("SELECT step FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
        row = await cur.fetchone()
    if row:
        await message.answer("Вы уже в системе.", reply_markup=main_kb)
        return
    await db.execute("INSERT OR REPLACE INTO users(user_id, step) VALUES(?, ?)", (message.from_user.id, "name"))
    await db.commit()
    await message.answer("Привет! Введи своё имя:")

@dp.message()
async def handler(message: types.Message):
    # получаем шаг
    async with db.execute("SELECT step FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await message.answer("Нажмите /start чтобы зарегистрироваться.")
        return
    step = row[0]
    if step == "name":
        await db.execute("UPDATE users SET name = ?, step = ? WHERE user_id = ?", (message.text, "age", message.from_user.id))
        await db.commit()
        await message.answer("Сколько вам лет?")
        return
    if step == "age":
        if not message.text.isdigit():
            await message.answer("Введите число.")
            return
        await db.execute("UPDATE users SET age = ?, step = ? WHERE user_id = ?", (int(message.text), "bio", message.from_user.id))
        await db.commit()
        await message.answer("Напишите пару слов о себе.")
        return
    if step == "bio":
        await db.execute("UPDATE users SET bio = ?, step = ? WHERE user_id = ?", (message.text, "done", message.from_user.id))
        await db.commit()
        await message.answer("Анкета сохранена.", reply_markup=main_kb)
        return

    # команды меню
    if message.text == "Моя анкета":
        async with db.execute("SELECT name, age, bio FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("Анкета не найдена. Нажмите /start")
            return
        name, age, bio = row
        await message.answer(f"Ваша анкета:\nИмя: {name}\nВозраст: {age}\nО себе: {bio}")
        return

    if message.text == "Смотреть анкеты":
        async with db.execute("SELECT user_id, name, age, bio FROM users WHERE step = 'done' AND user_id != ? ORDER BY RANDOM() LIMIT 1", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("Анкет других пользователей пока нет.")
            return
        uid, name, age, bio = row
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like:{uid}")],
            [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip:{uid}")]
        ])
        await message.answer(f"Имя: {name}\nВозраст: {age}\nО себе: {bio}", reply_markup=kb)
        return

@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    data = call.data or ""
    if data.startswith("like:"):
        liked_id = int(data.split(":", 1)[1])
        # сохраняем лайк
        await db.execute("INSERT OR IGNORE INTO likes(liker, liked) VALUES(?, ?)", (call.from_user.id, liked_id))
        await db.commit()
        # проверяем взаимность
        async with db.execute("SELECT 1 FROM likes WHERE liker = ? AND liked = ?", (liked_id, call.from_user.id)) as cur:
            rev = await cur.fetchone()
        if rev:
            await call.answer("Это матч! Отправлено уведомление.")
            try:
                await bot.send_message(liked_id, f"Вам поставили взаимный лайк — это матч с {call.from_user.first_name} ❤️")
            except Exception:
                pass
        else:
            await call.answer("Симпатия сохранена.")
            try:
                await bot.send_message(liked_id, f"Вам поставили лайк — {call.from_user.first_name} поставил(а) вам симпатию.")
            except Exception:
                pass
    elif data.startswith("skip:"):
        await call.answer("Пропущено.")

async def main():
    await init_db()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())

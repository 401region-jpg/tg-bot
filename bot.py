import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

API_TOKEN = "7517420285:AAEJMY567Htns_i3SbMqww5U0O_-TTjbPW8"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Моя анкета")],
        [KeyboardButton(text="Смотреть анкеты")],
        [KeyboardButton(text="Кто меня оценил")],
        [KeyboardButton(text="Мои мэтчи")]
    ],
    resize_keyboard=True
)

db = None

async def init_db():
    global db
    db = await aiosqlite.connect("db.sqlite3")
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        age INTEGER,
        bio TEXT,
        photo_id TEXT,
        step TEXT
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS likes(
        liker INTEGER,
        liked INTEGER,
        seen INTEGER DEFAULT 0,
        PRIMARY KEY(liker, liked)
    )
    """)
    await db.commit()

# --- регистрация
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with db.execute("SELECT step FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
        row = await cur.fetchone()
    if row:
        await message.answer("Вы уже зарегистрированы.", reply_markup=main_kb)
        return
    await db.execute(
        "INSERT OR REPLACE INTO users(user_id, username, step) VALUES(?, ?, ?)",
        (message.from_user.id, message.from_user.username, "name")
    )
    await db.commit()
    await message.answer("Привет! Введи своё имя:")

@dp.message()
async def handler(message: types.Message):
    async with db.execute("SELECT step FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await message.answer("Нажмите /start, чтобы зарегистрироваться.")
        return
    step = row[0]

    # шаги регистрации
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
        await db.execute("UPDATE users SET bio = ?, step = ? WHERE user_id = ?", (message.text, "photo", message.from_user.id))
        await db.commit()
        await message.answer("Теперь отправьте своё фото.")
        return

    if step == "photo":
        if not message.photo:
            await message.answer("Пожалуйста, отправьте фото.")
            return
        photo_id = message.photo[-1].file_id
        await db.execute("UPDATE users SET photo_id = ?, step = ? WHERE user_id = ?", (photo_id, "done", message.from_user.id))
        await db.commit()
        await message.answer("Анкета сохранена ✅", reply_markup=main_kb)
        return

    # меню
    if message.text == "Моя анкета":
        async with db.execute("SELECT name, age, bio, photo_id FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("Анкета не найдена. Нажмите /start")
            return
        name, age, bio, photo_id = row
        if photo_id:
            await message.answer_photo(photo_id, caption=f"Имя: {name}\nВозраст: {age}\nО себе: {bio}")
        else:
            await message.answer(f"Имя: {name}\nВозраст: {age}\nО себе: {bio}")
        return

    if message.text == "Смотреть анкеты":
        async with db.execute("""
            SELECT user_id, name, age, bio, photo_id, username
            FROM users
            WHERE step = 'done' AND user_id != ?
            ORDER BY RANDOM() LIMIT 1
        """, (message.from_user.id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer("Анкет других пользователей пока нет.")
            return
        uid, name, age, bio, photo_id, username = row
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like:{uid}")],
            [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip:{uid}")]
        ])
        text = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}"
        if username:
            text += f"\n@{username}"
        if photo_id:
            await message.answer_photo(photo_id, caption=text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        return

    if message.text == "Кто меня оценил":
        async with db.execute("""
            SELECT u.user_id, u.name, u.age, u.bio, u.photo_id, u.username
            FROM likes l
            JOIN users u ON l.liker = u.user_id
            WHERE l.liked = ? AND l.seen = 0
        """, (message.from_user.id,)) as cur:
            rows = await cur.fetchall()
        if not rows:
            await message.answer("Новых оценок нет.")
            return
        for uid, name, age, bio, photo_id, username in rows:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❤️ Взаимно", callback_data=f"like:{uid}")],
                [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip:{uid}")]
            ])
            text = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}"
            if username:
                text += f"\n@{username}"
            if photo_id:
                await message.answer_photo(photo_id, caption=text, reply_markup=kb)
            else:
                await message.answer(text, reply_markup=kb)
        await db.execute("UPDATE likes SET seen = 1 WHERE liked = ?", (message.from_user.id,))
        await db.commit()
        return

    if message.text == "Мои мэтчи":
        async with db.execute("""
            SELECT u.user_id, u.name, u.age, u.bio, u.photo_id, u.username
            FROM likes l1
            JOIN likes l2 ON l1.liker = l2.liked AND l1.liked = l2.liker
            JOIN users u ON u.user_id = l1.liked
            WHERE l1.liker = ?
        """, (message.from_user.id,)) as cur:
            rows = await cur.fetchall()
        if not rows:
            await message.answer("У вас пока нет мэтчей.")
            return
        for uid, name, age, bio, photo_id, username in rows:
            text = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}"
            if username:
                text += f"\n@{username}"
            if photo_id:
                await message.answer_photo(photo_id, caption=text)
            else:
                await message.answer(text)
        return

# --- лайки и пропуск
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    data = call.data or ""
    if data.startswith("like:"):
        liked_id = int(data.split(":", 1)[1])
        await db.execute("INSERT OR IGNORE INTO likes(liker, liked) VALUES(?, ?)", (call.from_user.id, liked_id))
        await db.commit()
        async with db.execute("SELECT 1 FROM likes WHERE liker = ? AND liked = ?", (liked_id, call.from_user.id)) as cur:
            rev = await cur.fetchone()
        if rev:
            await call.answer("Это матч! 🎉")
            try:
                await bot.send_message(liked_id, f"У вас мэтч с {call.from_user.first_name} (@{call.from_user.username}) ❤️")
            except Exception:
                pass
        else:
            await call.answer("Симпатия сохранена.")
    elif data.startswith("skip:"):
        await call.answer("Пропущено.")

# --- удаление анкеты при блокировке или очистке чата
@dp.my_chat_member()
async def handle_block(event: types.ChatMemberUpdated):
    if event.new_chat_member.status in ["kicked", "left"]:
        await db.execute("DELETE FROM users WHERE user_id = ?", (event.from_user.id,))
        await db.execute("DELETE FROM likes WHERE liker = ? OR liked = ?", (event.from_user.id, event.from_user.id))
        await db.commit()

# --- запуск
async def main():
    await init_db()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())

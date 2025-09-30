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
ADMIN_USERNAME = "lxsonen"  # только этот юзер может смотреть /admin

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Главное меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 Моя анкета")],
        [KeyboardButton(text="🔍 Смотреть анкеты")],
        [KeyboardButton(text="❤️ Мои мэтчи")]
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
        PRIMARY KEY(liker, liked)
    )
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS views(
        viewer INTEGER,
        viewed INTEGER,
        PRIMARY KEY(viewer, viewed)
    )
    """)
    await db.commit()

# --- регистрация
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with db.execute("SELECT step FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
        row = await cur.fetchone()
    if row:
        await message.answer("Вы уже зарегистрированы ✅", reply_markup=main_kb)
        return
    await db.execute(
        "INSERT OR REPLACE INTO users(user_id, username, step) VALUES(?, ?, ?)",
        (message.from_user.id, message.from_user.username, "name")
    )
    await db.commit()
    await message.answer("Привет! Введи своё имя:")

# --- админка
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.username != ADMIN_USERNAME:
        await message.answer("У вас недостаточно прав ❌")
        return

    # количество пользователей
    async with db.execute("SELECT COUNT(*) FROM users WHERE step='done'") as cur:
        users_count = (await cur.fetchone())[0]

    # количество лайков
    async with db.execute("SELECT COUNT(*) FROM likes") as cur:
        likes_count = (await cur.fetchone())[0]

    # количество мэтчей
    async with db.execute("""
        SELECT COUNT(*)
        FROM likes l1
        JOIN likes l2 ON l1.liker = l2.liked AND l1.liked = l2.liker
        WHERE l1.liker < l2.liker
    """) as cur:
        matches_count = (await cur.fetchone())[0]

    # сначала общая статистика
    text = (
        "📊 Статистика бота:\n\n"
        f"👤 Пользователей: {users_count}\n"
        f"❤️ Лайков: {likes_count}\n"
        f"💞 Мэтчей: {matches_count}\n\n"
        "📂 Анкеты:\n"
    )
    await message.answer(text)

    # теперь вывод всех анкет по одной
    async with db.execute("SELECT user_id, username, name, age, bio, photo_id FROM users WHERE step='done'") as cur:
        rows = await cur.fetchall()

    if not rows:
        await message.answer("Анкет пока нет.")
        return

    for uid, username, name, age, bio, photo_id in rows:
        caption = (
            f"ID: {uid}\n"
            f"Имя: {name}, {age}\n"
            f"@{username if username else '—'}\n"
            f"О себе: {bio}"
        )
        if photo_id:
            await message.answer_photo(photo_id, caption=caption)
        else:
            await message.answer(caption)

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

    # --- меню
    if message.text == "📄 Моя анкета":
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

    if message.text == "🔍 Смотреть анкеты":
        await show_next_profile(message.from_user.id)
        return

    if message.text == "❤️ Мои мэтчи":
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
            text = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}\n"
            if username:
                text += f"@{username}"
            if photo_id:
                await message.answer_photo(photo_id, caption=text)
            else:
                await message.answer(text)
        return

# --- функция показа следующей анкеты
async def show_next_profile(user_id: int):
    async with db.execute("""
        SELECT user_id, name, age, bio, photo_id
        FROM users
        WHERE step = 'done' AND user_id != ?
        AND user_id NOT IN (SELECT viewed FROM views WHERE viewer = ?)
        ORDER BY RANDOM() LIMIT 1
    """, (user_id, user_id)) as cur:
        row = await cur.fetchone()

    if not row:
        await db.execute("DELETE FROM views WHERE viewer = ?", (user_id,))
        await db.commit()
        await bot.send_message(user_id, "Анкеты закончились — начинаем заново! 🔄", reply_markup=main_kb)
        return

    uid, name, age, bio, photo_id = row
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like:{uid}")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip:{uid}")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]
    ])
    text = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}"
    if photo_id:
        await bot.send_photo(user_id, photo_id, caption=text, reply_markup=kb)
    else:
        await bot.send_message(user_id, text, reply_markup=kb)

# --- лайки и пропуск
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    data = call.data or ""
    if data == "menu":
        await call.message.answer("Вы вернулись в главное меню 🏠", reply_markup=main_kb)
        return

    if data.startswith("like:"):
        liked_id = int(data.split(":", 1)[1])
        await db.execute("INSERT OR IGNORE INTO likes(liker, liked) VALUES(?, ?)", (call.from_user.id, liked_id))
        await db.execute("INSERT OR IGNORE INTO views(viewer, viewed) VALUES(?, ?)", (call.from_user.id, liked_id))
        await db.commit()
        async with db.execute("SELECT username FROM users WHERE user_id = ?", (call.from_user.id,)) as cur:
            liker_username = (await cur.fetchone())[0]
        async with db.execute("SELECT 1 FROM likes WHERE liker = ? AND liked = ?", (liked_id, call.from_user.id)) as cur:
            rev = await cur.fetchone()
        if rev:
            await call.answer("Это мэтч! 🎉")
            try:
                if liker_username:
                    await bot.send_message(liked_id, f"У вас мэтч с @{liker_username} ❤️")
                else:
                    await bot.send_message(liked_id, f"У вас мэтч с {call.from_user.first_name} ❤️")
            except Exception:
                pass
        else:
            await call.answer("Симпатия сохранена.")
        await show_next_profile(call.from_user.id)

    elif data.startswith("skip:"):
        skipped_id = int(data.split(":", 1)[1])
        await db.execute("INSERT OR IGNORE INTO views(viewer, viewed) VALUES(?, ?)", (call.from_user.id, skipped_id))
        await db.commit()
        await call.answer("Пропущено.")
        await show_next_profile(call.from_user.id)

# --- удаление анкеты при блокировке
@dp.my_chat_member()
async def handle_block(event: types.ChatMemberUpdated):
    if event.new_chat_member.status in ["kicked", "left"]:
        await db.execute("DELETE FROM users WHERE user_id = ?", (event.from_user.id,))
        await db.execute("DELETE FROM likes WHERE liker = ? OR liked = ?", (event.from_user.id, event.from_user.id))
        await db.execute("DELETE FROM views WHERE viewer = ? OR viewed = ?", (event.from_user.id, event.from_user.id))
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

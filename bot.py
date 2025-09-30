import logging
import sqlite3
import asyncio
import random
import shutil
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher.filters import Text

# -----------------------------------
# Настройки
# -----------------------------------
TOKEN = "7517420285:AAEJMY567Htns_i3SbMqww5U0O_-TTjbPW8"
ADMIN_USERNAME = "@lxsonen"
ADMIN_ID = None  # Определим позже по username
DB_FILE = "database.db"
BACKUP_FILE = "database_backup.db"
MIN_AGE, MAX_AGE = 16, 30
SUPERLIKE_COOLDOWN = 24 * 3600  # 1 раз в сутки

# -----------------------------------
# Логирование
# -----------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------
# База данных
# -----------------------------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    age INTEGER,
    description TEXT,
    photo TEXT,
    last_active TIMESTAMP,
    superlike_used TIMESTAMP,
    ref_bonus INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER,
    to_id INTEGER,
    type TEXT
)""")

conn.commit()

# -----------------------------------
# Бот и диспетчер
# -----------------------------------
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# -----------------------------------
# Клавиатуры
# -----------------------------------
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("👤 Заполнить анкету заново")
main_kb.add("🔍 Смотреть анкеты", "💌 Мои мэтчи")
main_kb.add("⭐ Мой суперлайк", "👥 Посоветовать другу")

# -----------------------------------
# Вспомогательные функции
# -----------------------------------
def backup_db():
    try:
        shutil.copy(DB_FILE, BACKUP_FILE)
    except Exception as e:
        logger.error(f"Ошибка резервного копирования: {e}")

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def update_activity(user_id):
    cursor.execute("UPDATE users SET last_active=? WHERE user_id=?", (datetime.datetime.now(), user_id))
    conn.commit()

async def log_errors():
    while True:
        await asyncio.sleep(86400)  # раз в день
        try:
            await bot.send_message(ADMIN_ID, "ℹ️ Ежедневный отчёт: бот работает стабильно ✅")
        except Exception as e:
            logger.error(f"Ошибка отчета админу: {e}")

def cleanup_inactive():
    cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
    cursor.execute("DELETE FROM users WHERE last_active < ?", (cutoff,))
    conn.commit()

# -----------------------------------
# Хендлеры
# -----------------------------------
@dp.message_handler(commands=["start"])
async def start_cmd(msg: types.Message):
    global ADMIN_ID
    if msg.from_user.username == ADMIN_USERNAME.lstrip("@"):
        ADMIN_ID = msg.from_user.id

    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, last_active) VALUES (?, ?, ?)",
                   (msg.from_user.id, msg.from_user.username, datetime.datetime.now()))
    conn.commit()
    await msg.answer("👋 Добро пожаловать в бота знакомств! Заполни анкету:", reply_markup=main_kb)

@dp.message_handler(Text(equals="👤 Заполнить анкету заново"))
async def fill_profile(msg: types.Message):
    await msg.answer("Введите имя:")
    dp.register_message_handler(process_name, state="fill_name")

async def process_name(msg: types.Message):
    name = msg.text
    cursor.execute("UPDATE users SET name=? WHERE user_id=?", (name, msg.from_user.id))
    conn.commit()
    await msg.answer("Введите возраст:")
    dp.register_message_handler(process_age, state="fill_age")

async def process_age(msg: types.Message):
    try:
        age = int(msg.text)
    except:
        await msg.answer("Введите число")
        return
    if age < MIN_AGE:
        age = MIN_AGE
    elif age > MAX_AGE:
        age = MAX_AGE
    cursor.execute("UPDATE users SET age=? WHERE user_id=?", (age, msg.from_user.id))
    conn.commit()
    await msg.answer("Введите описание (до 1240 символов):")
    dp.register_message_handler(process_desc, state="fill_desc")

async def process_desc(msg: types.Message):
    text = msg.text[:1240]
    cursor.execute("UPDATE users SET description=? WHERE user_id=?", (text, msg.from_user.id))
    conn.commit()
    await msg.answer("Отправьте фото:")
    dp.register_message_handler(process_photo, content_types=["photo"], state="fill_photo")

async def process_photo(msg: types.Message):
    file_id = msg.photo[-1].file_id
    cursor.execute("UPDATE users SET photo=? WHERE user_id=?", (file_id, msg.from_user.id))
    conn.commit()
    await msg.answer("✅ Анкета сохранена!", reply_markup=main_kb)

@dp.message_handler(Text(equals="🔍 Смотреть анкеты"))
async def view_profiles(msg: types.Message):
    user = get_user(msg.from_user.id)
    if not user or not user[2] or not user[3]:
        await msg.answer("Сначала заполни анкету.")
        return
    cursor.execute("SELECT * FROM users WHERE user_id != ?", (msg.from_user.id,))
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Нет анкет.")
        return
    row = random.choice(rows)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👍 Лайк", callback_data=f"like_{row[0]}"))
    kb.add(InlineKeyboardButton("👎 Пропустить", callback_data=f"skip_{row[0]}"))
    kb.add(InlineKeyboardButton("⭐ Суперлайк", callback_data=f"superlike_{row[0]}"))
    await bot.send_photo(msg.chat.id, row[5], caption=f"{row[2]}, {row[3]}\n\n{row[4]}", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("like_") or c.data.startswith("superlike_") or c.data.startswith("skip_"))
async def process_like(call: types.CallbackQuery):
    user_id = call.from_user.id
    action, target = call.data.split("_")
    target_id = int(target)
    if action == "skip":
        await call.answer("Пропущено 👎")
    elif action == "like":
        cursor.execute("INSERT INTO likes (from_id, to_id, type) VALUES (?, ?, ?)", (user_id, target_id, "like"))
        conn.commit()
        await call.answer("Лайк 👍")
    elif action == "superlike":
        now = datetime.datetime.now()
        cursor.execute("SELECT superlike_used, ref_bonus FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        last_used, bonus = row
        if bonus > 0:
            cursor.execute("UPDATE users SET ref_bonus=ref_bonus-1 WHERE user_id=?", (user_id,))
            conn.commit()
            allowed = True
        elif not last_used or (now - datetime.datetime.fromisoformat(last_used)).total_seconds() > SUPERLIKE_COOLDOWN:
            cursor.execute("UPDATE users SET superlike_used=? WHERE user_id=?", (now, user_id))
            conn.commit()
            allowed = True
        else:
            allowed = False
        if allowed:
            cursor.execute("INSERT INTO likes (from_id, to_id, type) VALUES (?, ?, ?)", (user_id, target_id, "superlike"))
            conn.commit()
            await bot.send_message(target_id, f"🌟 Вас выбрали! {call.from_user.first_name} использовал суперлайк!")
            await call.answer("Суперлайк 🌟")
        else:
            await call.answer("Суперлайк можно использовать раз в сутки ❗")

@dp.message_handler(Text(equals="💌 Мои мэтчи"))
async def my_matches(msg: types.Message):
    cursor.execute("SELECT to_id FROM likes WHERE from_id=? AND type IN ('like','superlike')", (msg.from_user.id,))
    liked = [x[0] for x in cursor.fetchall()]
    cursor.execute("SELECT from_id FROM likes WHERE to_id=? AND type IN ('like','superlike')", (msg.from_user.id,))
    liked_back = [x[0] for x in cursor.fetchall()]
    matches = set(liked) & set(liked_back)
    if not matches:
        await msg.answer("Пока нет мэтчей 😔")
    else:
        for m in matches:
            user = get_user(m)
            if user:
                await msg.answer(f"🔥 У вас мэтч с {user[2]}, {user[3]}!")

@dp.message_handler(Text(equals="👥 Посоветовать другу"))
async def invite(msg: types.Message):
    await msg.answer("Пригласи друга: https://t.me/rsuhinlove_bot")

@dp.message_handler(commands=["admin"])
async def admin_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    text = msg.text.split(" ", 2)
    if len(text) >= 3 and text[1] == "message":
        message = text[2]
        cursor.execute("SELECT user_id FROM users")
        for row in cursor.fetchall():
            try:
                await bot.send_message(row[0], f"📢 Сообщение от админа: {message}")
            except:
                pass
        await msg.answer("Рассылка завершена ✅")
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]
        await msg.answer(f"👥 Пользователей: {users}")

# -----------------------------------
# Запуск
# -----------------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(log_errors())
    cleanup_inactive()
    backup_db()
    executor.start_polling(dp, skip_updates=True)

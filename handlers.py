# handlers.py
import asyncio
import datetime
import logging
from cachetools import TTLCache
from aiogram import types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from config import MIN_AGE, MAX_AGE, DESC_LIMIT, SUPERLIKE_COOLDOWN, REFERRAL_BONUS_DAYS, LAST_ACTIVE_UPDATE_MIN, ADMIN_ID, ADMIN_USERNAME
from states import ProfileStates, EditStates

logger = logging.getLogger(__name__)

# Простой rate limit (память по процессу)
_rate = {}

def rate_limited(user_id: int) -> bool:
    now = datetime.datetime.utcnow().timestamp()
    window = LAST_ACTIVE_UPDATE_MIN * 60 if LAST_ACTIVE_UPDATE_MIN else 300
    rec = _rate.get(user_id, [])
    # keep entries in window
    rec = [t for t in rec if now - t < window]
    if len(rec) >= 6:
        _rate[user_id] = rec
        return True
    rec.append(now)
    _rate[user_id] = rec
    return False

# Кеш кандидатов per user for short period
profiles_cache = TTLCache(maxsize=1000, ttl=300)

def main_menu_kb():
    # ✅ Исправлено: правильный синтаксис для aiogram 3.x
    kb = [
        [KeyboardButton(text="📄 Моя анкета")],
        [KeyboardButton(text="🔍 Смотреть анкеты"), KeyboardButton(text="❤️ Мои мэтчи")],
        [KeyboardButton(text="✏️ Заполнить анкету заново")],
        [KeyboardButton(text="👥 Посоветовать другу")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def profile_action_kb(target_id: int, super_available: bool = True):
    # ✅ Исправлено: правильный синтаксис для aiogram 3.x
    buttons = [
        [InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like:{target_id}")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip:{target_id}")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]
    ]
    if super_available:
        buttons.insert(1, [InlineKeyboardButton(text="🌟 Суперлайк", callback_data=f"superlike:{target_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Глобальный экземпляр бота (будет установлен в register_handlers)
bot_instance: Bot = None

async def show_next_profile(viewer_id: int):
    # try cache first
    cache_key = f"profiles_for_{viewer_id}"
    if cache_key in profiles_cache:
        row = profiles_cache[cache_key].pop() if profiles_cache[cache_key] else None
    else:
        row = await db.get_next_profile(viewer_id)
    if not row:
        await db.clear_views(viewer_id)
        # refresh and try one more time
        row = await db.get_next_profile(viewer_id)
        if not row:
            await bot_instance.send_message(viewer_id, "Анкет нет.", reply_markup=main_menu_kb())
            return

    # determine super availability
    user = await db.user_get(viewer_id)
    super_available = False
    if user:
        extra = user.get("superlike_extra") or 0
        extra_expires = user.get("superlike_extra_expires")
        if extra and extra_expires and extra_expires > datetime.datetime.utcnow():
            super_available = True
        else:
            last = user.get("last_superlike")
            if not last or (datetime.datetime.utcnow() - last).total_seconds() > SUPERLIKE_COOLDOWN:
                super_available = True

    # send profile
    caption = f"{row.get('name') or '—'}, {row.get('age') or '—'}\n\n{(row.get('bio') or '')[:DESC_LIMIT]}"
    kb = profile_action_kb(row.get("user_id"), super_available)
    try:
        if row.get("photo_id"):
            await bot_instance.send_photo(viewer_id, row.get("photo_id"), caption=caption, reply_markup=kb)
        else:
            await bot_instance.send_message(viewer_id, caption, reply_markup=kb)
    except Exception as e:
        logger.exception("send profile failed")

async def register_handlers(dp, database, bot: Bot):
    global db, bot_instance
    db = database
    bot_instance = bot

    # start
    @dp.message(Command("start"))
    async def cmd_start(msg: types.Message, state: FSMContext):
        # ✅ Исправлено: get_args заменён на split
        parts = msg.text.split()
        args = " ".join(parts[1:]) if len(parts) > 1 else ""
        ref = None
        if args.startswith("ref_"):
            try:
                ref = int(args.split("_", 1)[1])
            except:
                ref = None
        await db.user_create_if_missing(msg.from_user.id, msg.from_user.username, ref)
        # grant referral bonus
        if ref:
            ref_user = await db.user_get(ref)
            if ref_user:
                await db.user_update(ref, 
                    superlike_extra=(ref_user.get("superlike_extra", 0) + 1),
                    superlike_extra_expires=(datetime.datetime.utcnow() + datetime.timedelta(days=REFERRAL_BONUS_DAYS))
                )
        await db.user_update(msg.from_user.id, last_active=datetime.datetime.utcnow())
        # if admin and not set, set is_admin
        if msg.from_user.username and msg.from_user.username.lower() == ADMIN_USERNAME.lower():
            await db.user_update(msg.from_user.id, is_admin=True)
        u = await db.user_get(msg.from_user.id)
        if u and u.get("step") == "done":
            await msg.answer("С возвращением.", reply_markup=main_menu_kb())
            return
        await state.set_state(ProfileStates.name)
        await msg.answer("Введите имя (3-50 символов):", reply_markup=main_menu_kb())

    # registration FSM
    @dp.message(ProfileStates.name)
    async def reg_name(msg: types.Message, state: FSMContext):
        text = (msg.text or "").strip()
        if len(text) < 3 or len(text) > 50:
            await msg.answer("Имя должно быть 3–50 символов. Повторите:")
            return
        await state.update_data(name=text)
        await state.set_state(ProfileStates.age)
        await msg.answer("Введите возраст (16-30):")

    @dp.message(ProfileStates.age)
    async def reg_age(msg: types.Message, state: FSMContext):
        try:
            age = int(msg.text)
        except:
            await msg.answer("Введите число.")
            return
        if age < MIN_AGE:
            age = MIN_AGE
        if age > MAX_AGE:
            age = MAX_AGE
        await state.update_data(age=age)
        await state.set_state(ProfileStates.bio)
        await msg.answer(f"Введите описание (до {DESC_LIMIT} символов):")

    @dp.message(ProfileStates.bio)
    async def reg_bio(msg: types.Message, state: FSMContext):
        text = (msg.text or "")[:DESC_LIMIT]
        await state.update_data(bio=text)
        await state.set_state(ProfileStates.photo)
        await msg.answer("Отправьте фото как фото (не файл):")

    @dp.message(ProfileStates.photo, F.photo)
    async def reg_photo(msg: types.Message, state: FSMContext):
        data = await state.get_data()
        photo_id = msg.photo[-1].file_id
        # write to db
        await db.user_update(msg.from_user.id,
                             username=msg.from_user.username,
                             name=data["name"],
                             age=data["age"],
                             bio=data["bio"],
                             photo_id=photo_id,
                             step="done",
                             last_active=datetime.datetime.utcnow())
        await state.clear()
        await msg.answer("Анкета сохранена ✅", reply_markup=main_menu_kb())

    # show profile / browsing
    @dp.message(F.text == "🔍 Смотреть анкеты")
    async def browse(msg: types.Message):
        if rate_limited(msg.from_user.id):
            await msg.answer("Слишком часто. Подождите.")
            return
        u = await db.user_get(msg.from_user.id)
        if not u or u.get("step") != "done":
            await msg.answer("Сначала заполните анкету.")
            return
        await show_next_profile(msg.from_user.id)

    # callbacks: like/superlike/skip
    @dp.callback_query(lambda c: c.data and c.data.startswith(("like:", "superlike:", "skip:")))
    async def handle_reaction(cq: types.CallbackQuery):
        user_id = cq.from_user.id
        action, sid = cq.data.split(":", 1)
        try:
            target = int(sid)
        except:
            await cq.answer("Ошибка данных.")
            return

        if action == "skip":
            await db.add_view(user_id, target)
            await cq.answer("Пропущено")
            await cq.message.delete()
            await show_next_profile(user_id)
            return

        if action == "like":
            await db.insert_like(user_id, target, "like")
            await db.add_view(user_id, target)
            mutual = await db.exists_mutual(user_id, target)
            if mutual:
                match_id = await db.create_match(user_id, target)
                # notify other: send non-invasive notice with button to view
                try:
                    await bot_instance.send_message(target, "💌 Вам поставили симпатию! Нажмите, чтобы посмотреть.", 
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👀 Посмотреть", callback_data=f"viewmatch:{match_id}")]
                        ]))
                except Exception:
                    pass
                await cq.answer("Это мэтч! 🎉")
            else:
                await cq.answer("Лайк сохранён")
            await cq.message.delete()
            await show_next_profile(user_id)
            return

        if action == "superlike":
            # check availability
            u = await db.user_get(user_id)
            allowed = False
            if u:
                extra = u.get("superlike_extra") or 0
                extra_expires = u.get("superlike_extra_expires")
                if extra and extra_expires and extra_expires > datetime.datetime.utcnow():
                    allowed = True
                    await db.user_update(user_id, superlike_extra=extra - 1)
                else:
                    last = u.get("last_superlike")
                    if not last or (datetime.datetime.utcnow() - last).total_seconds() > SUPERLIKE_COOLDOWN:
                        allowed = True
                        await db.user_update(user_id, last_superlike=datetime.datetime.utcnow())

            if not allowed:
                await cq.answer("Суперлайк доступен 1 раз в 24 часа или по реф. бонусу.")
                return

            # record superlike
            await db.insert_like(user_id, target, "superlike")
            await db.add_view(user_id, target)
            mutual = await db.exists_mutual(user_id, target)
            if mutual:
                match_id = await db.create_match(user_id, target)
                # notify target that someone superliked them (with username)
                try:
                    name = (await db.user_get(user_id)).get("username") or cq.from_user.first_name
                    await bot_instance.send_message(target, f"🌟 Вас выбрали! @{name} использовал(а) Суперлайк!", 
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👀 Посмотреть", callback_data=f"viewmatch:{match_id}")]
                        ]))
                except Exception:
                    pass
                await cq.answer("Суперлайк и мэтч!")
            else:
                try:
                    name = (await db.user_get(user_id)).get("username") or cq.from_user.first_name
                    await bot_instance.send_message(target, f"🌟 У вас суперлайк от @{name}! Нажмите, чтобы посмотреть.", 
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👀 Посмотреть", callback_data="noop")]
                        ]))
                except Exception:
                    pass
                await cq.answer("Суперлайк отправлен.")
            await cq.message.delete()
            await show_next_profile(user_id)
            return

    # view match button handler
    @dp.callback_query(lambda c: c.data and c.data.startswith("viewmatch:"))
    async def view_match(cq: types.CallbackQuery):
        mid = int(cq.data.split(":", 1)[1])
        rows = await db.get_unshown_matches(cq.from_user.id)
        match = None
        for r in rows:
            if r["id"] == mid:
                match = r
                break
        if not match:
            await cq.answer("Мэтч не найден")
            return
        other = match["user_b"] if match["user_a"] == cq.from_user.id else match["user_a"]
        u_other = await db.user_get(other)
        if not u_other:
            await cq.answer("Профиль не найден")
            return
        caption = f"Имя: {u_other.get('name')}\nВозраст: {u_other.get('age')}\nО себе: {u_other.get('bio')}"
        try:
            if u_other.get("photo_id"):
                await bot_instance.send_photo(cq.from_user.id, u_other.get("photo_id"), caption=caption)
            else:
                await bot_instance.send_message(cq.from_user.id, caption)
        except:
            pass
        await db.mark_match_shown(mid, cq.from_user.id)
        await cq.answer()

    # my matches command by button
    @dp.message(F.text == "❤️ Мои мэтчи")
    async def my_matches(msg: types.Message):
        rows = await db.get_unshown_matches(msg.from_user.id)
        if not rows:
            await msg.answer("Новых мэтчей нет.")
            return
        for r in rows:
            other = r["user_b"] if r["user_a"] == msg.from_user.id else r["user_a"]
            u = await db.user_get(other)
            if not u:
                continue
            caption = f"Имя: {u.get('name')}\nВозраст: {u.get('age')}\nО себе: {u.get('bio')}"
            if u.get("photo_id"):
                await msg.answer_photo(u.get("photo_id"), caption=caption)
            else:
                await msg.answer(caption)
            await db.mark_match_shown(r["id"], msg.from_user.id)

    # admin command: stats + broadcast
    @dp.message(Command("admin"))
    async def admin_cmd(msg: types.Message):
        # check if allowed
        allowed = False
        if msg.from_user.id == ADMIN_ID:
            allowed = True
        else:
            u = await db.user_get(msg.from_user.id)
            if u and u.get("is_admin"):
                allowed = True
        if not allowed:
            await msg.answer("Недостаточно прав")
            return
        parts = (msg.text or "").split(" ", 2)
        if len(parts) >= 3 and parts[1].lower() == "message":
            body = parts[2]
            users = await db.all_users()
            sent = 0
            for u in users:
                try:
                    await bot_instance.send_message(u["user_id"], f"📢 От админа:\n\n{body}")
                    sent += 1
                except:
                    pass
            await msg.answer(f"Отправлено: {sent}")
            return
        # show stats: total, active last hour, matches today, new today
        users = await db.all_users()
        total = len(users)
        hour_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        active = sum(1 for u in users if u.get("last_active") and datetime.datetime.fromisoformat(u["last_active"]) > hour_ago)
        # Для matches_today и new_today нужно будет добавить поля created_at в SQLite
        await msg.answer(f"Всего: {total}\nАктивных (1ч): {active}\n(Подробная статистика требует доработки БД)")

    # invite/referral
    @dp.message(F.text == "👥 Посоветовать другу")
    async def invite(msg: types.Message):
        me = await bot_instance.get_me()
        link = f"https://t.me/{me.username}?start=ref_{msg.from_user.id}"
        await msg.answer(f"Поделитесь ссылкой: {link}\nЗа регистрацию по ссылке реферер получает +1 Суперлайк на {REFERRAL_BONUS_DAYS} дня.")

    # my profile view and edit buttons
    @dp.message(F.text == "📄 Моя анкета")
    async def my_profile(msg: types.Message):
        u = await db.user_get(msg.from_user.id)
        if not u or u.get("step") != "done":
            await msg.answer("Анкета не заполнена. Нажмите 'Заполнить анкету заново'")
            return
        caption = f"Имя: {u.get('name')}\nВозраст: {u.get('age')}\nО себе: {u.get('bio')}\n@{u.get('username')}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_name"),
                InlineKeyboardButton(text="✏️ Изменить возраст", callback_data="edit_age")
            ],
            [
                InlineKeyboardButton(text="✏️ Изменить описание", callback_data="edit_bio"),
                InlineKeyboardButton(text="📷 Поменять фото", callback_data="edit_photo")
            ],
            [
                InlineKeyboardButton(text="Заполнить заново", callback_data="re_full")
            ]
        ])
        if u.get("photo_id"):
            await msg.answer_photo(u.get("photo_id"), caption=caption, reply_markup=kb)
        else:
            await msg.answer(caption, reply_markup=kb)

    # edit callbacks
    @dp.callback_query(lambda c: c.data in ("edit_name", "edit_age", "edit_bio", "edit_photo", "re_full"))
    async def handle_edit(cq: types.CallbackQuery, state: FSMContext):
        if cq.data == "edit_name":
            await state.set_state(EditStates.edit_name)
            await cq.message.answer("Введите новое имя:")
        elif cq.data == "edit_age":
            await state.set_state(EditStates.edit_age)
            await cq.message.answer("Введите новый возраст:")
        elif cq.data == "edit_bio":
            await state.set_state(EditStates.edit_bio)
            await cq.message.answer("Введите новое описание:")
        elif cq.data == "edit_photo":
            await state.set_state(EditStates.edit_photo)
            await cq.message.answer("Отправьте новое фото:")
        elif cq.data == "re_full":
            await state.set_state(ProfileStates.name)
            await cq.message.answer("Начинаем заново. Введите имя:")
        await cq.answer()

    # handlers for edit states
    @dp.message(EditStates.edit_name)
    async def do_edit_name(msg: types.Message, state: FSMContext):
        text = (msg.text or "").strip()
        if len(text) < 3 or len(text) > 50:
            await msg.answer("Имя 3-50 символов.")
            return
        await db.user_update(msg.from_user.id, name=text)
        await state.clear()
        await msg.answer("Имя обновлено.", reply_markup=main_menu_kb())

    @dp.message(EditStates.edit_age)
    async def do_edit_age(msg: types.Message, state: FSMContext):
        try:
            age = int(msg.text)
        except:
            await msg.answer("Введите число")
            return
        if age < MIN_AGE:
            age = MIN_AGE
        if age > MAX_AGE:
            age = MAX_AGE
        await db.user_update(msg.from_user.id, age=age)
        await state.clear()
        await msg.answer("Возраст обновлён.", reply_markup=main_menu_kb())

    @dp.message(EditStates.edit_bio)
    async def do_edit_bio(msg: types.Message, state: FSMContext):
        text = (msg.text or "")[:DESC_LIMIT]
        await db.user_update(msg.from_user.id, bio=text)
        await state.clear()
        await msg.answer("Описание обновлено.", reply_markup=main_menu_kb())

    @dp.message(EditStates.edit_photo, F.photo)
    async def do_edit_photo(msg: types.Message, state: FSMContext):
        pid = msg.photo[-1].file_id
        await db.user_update(msg.from_user.id, photo_id=pid)
        await state.clear()
        await msg.answer("Фото обновлено.", reply_markup=main_menu_kb())
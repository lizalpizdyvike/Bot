import asyncio
import logging
import aiohttp
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import qrcode
from io import BytesIO
from zoneinfo import ZoneInfo
from urllib.parse import quote

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "8319221865:AAGy4cA5k9XRWHV4q4zcbieJ9r_KE-aUFjQ"
OWNER_ID = 7616322842
TEXT_API_URL = "http://api.onlysq.ru/ai/v2"
MODEL_TEXT = "gpt-4o-mini"

DB_FILE = "chat_history.json"
IMAGE_LIMIT_FILE = "image_limits.json"
MSK = ZoneInfo("Europe/Moscow")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

user_mode = {}
bot_create_state = {}
broadcast_state = {}

# ================== JSON ==================
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def add_user(user):
    data = load_json(DB_FILE)
    uid = str(user.id)

    if uid in data:
        return

    # сохраняем пользователя
    data[uid] = {"joined": datetime.now().isoformat()}
    save_json(DB_FILE, data)

    # уведомление овнера
    text = (
        "👤 *Новый пользователь*\n\n"
        f"Имя: {user.full_name}\n"
        f"Username: @{user.username if user.username else 'нет'}\n"
        f"ID: `{user.id}`"
    )

    try:
        photos = await bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            await bot.send_photo(
                OWNER_ID,
                file_id,
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                OWNER_ID,
                text,
                parse_mode="Markdown"
            )
    except:
        await bot.send_message(
            OWNER_ID,
            text,
            parse_mode="Markdown"
        )

def get_all_users():
    return list(load_json(DB_FILE).keys())

# ================== КЛАВИАТУРЫ ==================
def main_menu(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 AI", callback_data="ai")
    kb.button(text="📷 QR", callback_data="qr")
    kb.button(text="🛠 Создать бота", callback_data="create_bot")
    kb.button(text="🖼️ Генерация фото", callback_data="image")
    if user_id == OWNER_ID:
        kb.button(text="👑 Admin", callback_data="admin")
    kb.adjust(1)
    return kb.as_markup()

def back_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="back")
    return kb.as_markup()

def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Рассылка", callback_data="broadcast")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1)
    return kb.as_markup()

# ================== AI ==================
async def ai_request(uid, text):
    headers = {"Authorization": "Bearer openai"}
    payload = {
        "model": MODEL_TEXT,
        "request": {
            "messages": [{"role": "user", "content": text}]
        }
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(TEXT_API_URL, json=payload, headers=headers) as r:
            data = await r.json()
            return data["choices"][0]["message"]["content"]

# ================== IMAGE ==================
def can_generate_image(uid):
    data = load_json(IMAGE_LIMIT_FILE)
    uid = str(uid)
    today = datetime.now(MSK).strftime("%Y-%m-%d")

    if uid not in data or data[uid]["date"] != today:
        data[uid] = {"date": today, "count": 0}

    if data[uid]["count"] >= 5:
        return False

    data[uid]["count"] += 1
    save_json(IMAGE_LIMIT_FILE, data)
    return True

async def generate_image(prompt):
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.read()

# ================== START ==================
@dp.message(CommandStart())
async def start(m: Message):
    await add_user(m.from_user)

    await m.answer(
        "👋 Привет!\n\nВыбери кнопку ниже 👇",
        reply_markup=main_menu(m.from_user.id)
    )

# ================== CALLBACKS ==================
@dp.callback_query(F.data == "back")
async def back(c):
    await add_user(c.from_user)
    user_mode[c.from_user.id] = "menu"
    broadcast_state.pop(c.from_user.id, None)
    await c.message.edit_text("Главное меню 👇", reply_markup=main_menu(c.from_user.id))

@dp.callback_query(F.data == "ai")
async def ai_mode(c):
    await add_user(c.from_user)
    user_mode[c.from_user.id] = "ai"
    await c.message.edit_text("🤖 Напиши сообщение", reply_markup=back_menu())

@dp.callback_query(F.data == "qr")
async def qr_mode(c):
    await add_user(c.from_user)
    user_mode[c.from_user.id] = "qr"
    await c.message.edit_text("📷 Отправь текст", reply_markup=back_menu())

@dp.callback_query(F.data == "image")
async def image_mode(c):
    await add_user(c.from_user)
    user_mode[c.from_user.id] = "image"
    await c.message.edit_text("🖼 Опиши изображение", reply_markup=back_menu())

@dp.callback_query(F.data == "create_bot")
async def create_bot(c):
    await add_user(c.from_user)
    user_mode[c.from_user.id] = "create_bot"
    bot_create_state[c.from_user.id] = {"step": 1}
    await c.message.edit_text("🔑 Отправь токен бота", reply_markup=back_menu())

@dp.callback_query(F.data == "admin")
async def admin(c):
    await add_user(c.from_user)
    if c.from_user.id == OWNER_ID:
        await c.message.edit_text("👑 Admin", reply_markup=admin_menu())

@dp.callback_query(F.data == "broadcast")
async def broadcast_start(c):
    await add_user(c.from_user)
    if c.from_user.id != OWNER_ID:
        return
    broadcast_state[c.from_user.id] = "text"
    await c.message.edit_text("📢 Отправь текст рассылки", reply_markup=back_menu())

# ================== TEXT ==================
@dp.message(F.text)
async def text_handler(m: Message):
    await add_user(m.from_user)

    uid = m.from_user.id
    mode = user_mode.get(uid)

    if broadcast_state.get(uid) == "text":
        for u in get_all_users():
            try:
                await bot.send_message(int(u), m.text)
                await asyncio.sleep(0.05)
            except:
                pass
        broadcast_state.pop(uid)
        await m.answer("✅ Рассылка завершена", reply_markup=main_menu(uid))
        return

    if mode == "image":
        if not can_generate_image(uid):
            await m.answer("❌ Лимит 5 изображений в день")
            return
        img = await generate_image(m.text)
        await m.answer_photo(BufferedInputFile(img, "image.png"))
        return

    if mode == "qr":
        img = qrcode.make(m.text)
        bio = BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)
        await m.answer_photo(BufferedInputFile(bio.read(), "qr.png"))
        return

    if mode == "create_bot":
        state = bot_create_state[uid]
        if state["step"] == 1:
            state["token"] = m.text
            state["step"] = 2
            await m.answer("📝 Опиши, что должен делать бот")
            return
        code = await ai_request(uid, f"Создай бота aiogram 3. {m.text}")
        await m.answer_document(BufferedInputFile(code.encode(), "bot.py"))
        await m.answer("✅ Бот создан", reply_markup=main_menu(uid))
        user_mode[uid] = "menu"
        return

    if mode == "ai":
        reply = await ai_request(uid, m.text)
        await m.answer(reply)
        return

# ================== MAIN ==================
async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

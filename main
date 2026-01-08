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
import re

TELEGRAM_TOKEN = "8319221865:AAGy4cA5k9XRWHV4q4zcbieJ9r_KE-aUFjQ"
API_URL = "http://api.onlysq.ru/ai/v2"
MODEL = "gpt-4o-mini"
OWNER_ID = 7616322842

DB_FILE = "chat_history.json"
MAX_MESSAGE_LENGTH = 4000

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
user_mode = {}

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_message(user_id, role, content):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = []
    db[uid].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    save_db(db)

def get_history(user_id, limit=30):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        return []
    return [{"role": m["role"], "content": m["content"]} for m in db[uid][-limit:]]

def clear_history(user_id):
    db = load_db()
    db[str(user_id)] = []
    save_db(db)

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 AI", callback_data="chat_ai")
    kb.button(text="📷 QR", callback_data="qr_mode")
    kb.adjust(1)
    return kb.as_markup()

def back_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="back_menu")
    kb.adjust(1)
    return kb.as_markup()

def split_message(text):
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]
    parts = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            parts.append(text)
            break
        pos = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if pos == -1:
            pos = text.rfind(' ', 0, MAX_MESSAGE_LENGTH)
        if pos == -1:
            pos = MAX_MESSAGE_LENGTH
        parts.append(text[:pos])
        text = text[pos:].lstrip()
    return parts

async def send_long(message, text):
    for i, part in enumerate(split_message(text)):
        if i:
            await asyncio.sleep(0.4)
        await message.answer(part)

async def get_ai_response(uid, text):
    headers = {"Authorization": "Bearer openai"}
    history = get_history(uid, 25)

    messages = [
        {"role": "system", "content": "Отвечай чётко. Если просят код — только код в ```"}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    payload = {
        "model": MODEL,
        "request": {"messages": messages, "temperature": 0.7}
    }

    for _ in range(2):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
                async with s.post(API_URL, json=payload, headers=headers) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    reply = data["choices"][0]["message"]["content"]
                    save_message(uid, "user", text)
                    save_message(uid, "assistant", reply)
                    return reply
        except Exception as e:
            logging.error(e)

    return "Ошибка. Попробуйте позже."

def extract_code(text: str):
    block = re.findall(r"```(?:[\w]+)?\n([\s\S]*?)```", text)
    if block:
        return block[0].strip()
    return None

async def notify_owner(message: Message):
    try:
        user = message.from_user
        photos = await bot.get_user_profile_photos(user.id, limit=1)
        caption = (
            "Новый пользователь\n\n"
            f"Имя: {user.full_name}\n"
            f"Username: @{user.username if user.username else 'нет'}\n"
            f"ID: {user.id}"
        )
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            await bot.send_photo(OWNER_ID, file_id, caption=caption)
        else:
            await bot.send_message(OWNER_ID, caption)
    except:
        pass

@dp.message(CommandStart())
async def start(message: Message):
    user_mode[message.from_user.id] = "menu"
    await notify_owner(message)
    await message.answer("Готов.", reply_markup=main_menu())

@dp.callback_query(F.data == "chat_ai")
async def chat_ai(callback):
    user_mode[callback.from_user.id] = "chat"
    await callback.message.edit_text(".", reply_markup=back_menu())

@dp.callback_query(F.data == "qr_mode")
async def qr_mode(callback):
    user_mode[callback.from_user.id] = "qr"
    await callback.message.edit_text(".", reply_markup=back_menu())

@dp.callback_query(F.data == "back_menu")
async def back_menu_btn(callback):
    user_mode[callback.from_user.id] = "menu"
    await callback.message.edit_text("Готов.", reply_markup=main_menu())

@dp.message(F.text == "/clear")
async def clear_cmd(message: Message):
    clear_history(message.from_user.id)
    user_mode[message.from_user.id] = "chat"
    await message.answer("Очищено.")

@dp.message(F.text == "/history")
async def history_cmd(message: Message):
    hist = get_history(message.from_user.id, 12)
    if not hist:
        await message.answer("Пусто.")
        return
    text = ""
    for m in hist:
        icon = "👤" if m["role"] == "user" else "🤖"
        text += f"{icon} {m['content'][:300]}\n\n"
    await send_long(message, text)

async def send_qr(message: Message, text: str):
    img = qrcode.make(text)
    bio = BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    await message.answer_photo(
        BufferedInputFile(bio.read(), filename="qr.png"),
        caption="QR"
    )

@dp.message(F.text)
async def handle_text(message: Message):
    uid = message.from_user.id
    mode = user_mode.get(uid, "menu")

    if mode == "menu":
        await message.answer(".", reply_markup=main_menu())
        return

    if mode == "qr":
        if not message.text.startswith("http"):
            await message.answer("Ошибка.")
            return
        await send_qr(message, message.text)
        return

    if mode == "chat":
        thinking = await message.answer("…")
        await bot.send_chat_action(message.chat.id, "typing")
        answer = await get_ai_response(uid, message.text)
        await thinking.delete()
        code = extract_code(answer)

        if code:
            file = BufferedInputFile(code.encode("utf-8"), filename="ai_code.py")
            await message.answer_document(file, caption="Код")
        else:
            await send_long(message, answer)

async def main():
    logging.info("Запуск")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


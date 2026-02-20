import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ===== CONFIG =====
TELEGRAM_TOKEN = "8386816504:AAEE4eByAWBojkr5GjHOuPqELOjwgT9d-ZQ"
CHANNEL_ID = -1003839610709

API_URL = "http://api.onlysq.ru/ai/v2"
MODEL = "gpt-4o-mini"
STICKER_ID = "CAACAgIAAxkBAAIZemmYUVN88dYZTh0-80wf1_wbDK21AAIxJgACEBSRS8-bcxFm6MIfOgQ"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
session: aiohttp.ClientSession | None = None

# ===== STATE =====
user_mode: dict[int, str] = {}
user_memory: dict[int, list[dict]] = {}

# ===== SUB CHECK =====
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.warning(f"SUB ERROR {user_id}: {e}")
        return False

# ===== KEYBOARDS =====
sub_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔥 Подписаться", url="https://t.me/crashkids")],
    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
])

def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🤖 AI", callback_data="chat_ai")
    kb.button(text="🗑️ Сбросить память", callback_data="reset_memory")
    kb.adjust(1)
    return kb.as_markup()

def back_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="back_menu")
    return kb.as_markup()

# ===== AI FUNCTION =====
async def get_ai_response(user_id: int, prompt: str) -> str:
    if not session:
        raise RuntimeError("Session not initialized")
    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": prompt})
    headers = {"Authorization": "Bearer openai"}
    payload = {"model": MODEL, "request": {"messages": user_memory[user_id]}}

    try:
        async with session.post(API_URL, json=payload, headers=headers, timeout=60) as resp:
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                return "❌ Ошибка AI: пустой ответ"
            msg = choices[0].get("message", {}).get("content", "")
            if not msg:
                return "❌ Ошибка AI: пустой ответ"
            user_memory[user_id].append({"role": "assistant", "content": msg})
            return msg
    except Exception as e:
        logging.exception(f"AI ERROR: {e}")
        return f"❌ Ошибка AI: {e}"

# ===== START HANDLER =====
@dp.message(CommandStart())
async def start_handler(message: Message):
    if not await is_subscribed(message.from_user.id):
        await message.answer("❌ Подпишись на @crashkids", reply_markup=sub_kb)
        return

    user_mode[message.from_user.id] = "chat"
    await message.answer_sticker(STICKER_ID)
    await message.answer(
        "🔥 Привет! Я нейросеть. Напиши что-нибудь — я отвечу!",
        reply_markup=main_menu()
    )

# ===== CALLBACK HANDLERS =====
@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.edit_text("✅ Подписка подтверждена! Напиши /start")
    else:
        await call.answer("❌ Ты не подписан!", show_alert=True)

@dp.callback_query(F.data == "chat_ai")
async def chat_ai(call: CallbackQuery):
    user_mode[call.from_user.id] = "chat"
    await call.message.edit_text("🤖 AI режим включен", reply_markup=back_menu())

@dp.callback_query(F.data == "reset_memory")
async def reset_memory(call: CallbackQuery):
    user_memory[call.from_user.id] = []
    await call.answer("🗑️ Память сброшена!", show_alert=True)

@dp.callback_query(F.data == "back_menu")
async def back_menu_callback(call: CallbackQuery):
    user_mode[call.from_user.id] = "chat"
    await call.message.edit_text("Главное меню", reply_markup=main_menu())

# ===== CHAT WITH SYNCHRONOUS PROGRESS =====
@dp.message(F.text)
async def chat(message: Message):
    if not await is_subscribed(message.from_user.id):
        await message.answer("❌ Подпишись!", reply_markup=sub_kb)
        return

    if user_mode.get(message.from_user.id) != "chat":
        return

    # Отправляем пустое сообщение с прогрессом
    progress_msg = await message.answer("🤔 Думает .. 1%")

    # Запускаем AI запрос параллельно
    ai_task = asyncio.create_task(get_ai_response(message.from_user.id, message.text))

    # Прогресс шагами
    progress_steps = [1,6,19,25,38,46,58,69,73,78,87,94,98,100]
    for p in progress_steps:
        dots = "." * ((p // 10) % 3 + 1)
        try:
            await progress_msg.edit_text(f"🤔 Думает {dots} {p}%")
        except Exception:
            pass
        # Flood control Telegram
        if p % 20 == 0 or p == 100:
            await bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(0.1)  # быстрый, плавный прогресс

    # Ждём ответ AI, если ещё не готов
    answer = await ai_task
    await progress_msg.edit_text(f"💬 Ответ:\n{answer}")

# ===== MAIN =====
async def main():
    global session
    session = aiohttp.ClientSession()
    logging.info("🚀 BOT RUNNING WITH MODEL: GPT-4o-mini")
    try:
        await dp.start_polling(bot)
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())

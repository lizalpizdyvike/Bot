import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramForbiddenError

# ================= НАСТРОЙКИ =================

BOT_TOKEN = "8209848374:AAEBh4Mceach2GYzk4QRCWwa-zUkVewNfLQ"

# ================= ЛОГИ ======================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

def log(text: str):
    logging.info(text)

# ================= ОБЪЕКТЫ ===================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================= СОСТОЯНИЕ =================

@dataclass
class ChannelConfig:
    interval: int = 5
    limit: int = 10
    enabled: bool = False
    sent: int = 0
    task: asyncio.Task | None = None

channels: dict[int, ChannelConfig] = {}
user_selected_channel: dict[int, int] = {}

# ================= АКТИВНОСТЬ =================

async def activity_loop(channel_id: int):
    cfg = channels[channel_id]
    log(f"🟢 Activity STARTED | channel_id={channel_id}")

    while cfg.enabled and cfg.sent < cfg.limit:
        await asyncio.sleep(cfg.interval * 60)

        try:
            log(f"➡️ Trying to send ping | channel_id={channel_id}")

            msg = await bot.send_message(channel_id, ".")
            await asyncio.sleep(1)
            await bot.delete_message(channel_id, msg.message_id)

            cfg.sent += 1
            log(f"✅ Ping {cfg.sent}/{cfg.limit} SENT | channel_id={channel_id}")

        except TelegramForbiddenError as e:
            log(f"⛔ FORBIDDEN | No rights in channel {channel_id}")
            cfg.enabled = False
            break

        except Exception as e:
            log(f"❌ ERROR | channel_id={channel_id} | {e}")
            await asyncio.sleep(10)

    cfg.enabled = False
    log(f"🔴 Activity FINISHED | channel_id={channel_id}")

# ================= СОБЫТИЯ ===================

@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    chat = event.chat
    status = event.new_chat_member.status

    if chat.type == ChatType.CHANNEL and status == ChatMemberStatus.ADMINISTRATOR:
        channels.setdefault(chat.id, ChannelConfig())
        log(f"🤖 Bot ADMIN in channel {chat.id} ({chat.title})")

# ================= КОМАНДЫ (ЛС) =================

@router.message(CommandStart())
async def start_cmd(msg: Message):
    await msg.answer(
        "🤖 Управление каналами\n\n"
        "Команды:\n"
        "/channels\n"
        "/select <id>\n"
        "/set <мин> <кол-во>\n"
        "/start_activity\n"
        "/stop_activity\n"
        "/status"
    )

@router.message(Command("channels"))
async def list_channels(msg: Message):
    if not channels:
        await msg.answer("Нет каналов")
        return

    text = "📡 Каналы:\n"
    for cid in channels:
        text += f"- `{cid}`\n"

    await msg.answer(text, parse_mode="Markdown")

@router.message(Command("select"))
async def select_channel(msg: Message):
    cid = int(msg.text.split()[1])
    if cid not in channels:
        await msg.answer("Канал не найден")
        return

    user_selected_channel[msg.from_user.id] = cid
    await msg.answer(f"✅ Канал выбран: `{cid}`", parse_mode="Markdown")

def selected_channel(user_id: int):
    return user_selected_channel.get(user_id)

@router.message(Command("set"))
async def set_cmd(msg: Message):
    cid = selected_channel(msg.from_user.id)
    if not cid:
        await msg.answer("Сначала /select")
        return

    minutes, limit = map(int, msg.text.split()[1:])
    cfg = channels[cid]
    cfg.interval = minutes
    cfg.limit = limit
    cfg.sent = 0

    log(f"⚙️ Settings | channel_id={cid}")
    await msg.answer("⚙️ Настройки сохранены")

@router.message(Command("start_activity"))
async def start_activity(msg: Message):
    cid = selected_channel(msg.from_user.id)
    if not cid:
        await msg.answer("Сначала /select")
        return

    cfg = channels[cid]
    if cfg.enabled:
        await msg.answer("Уже работает")
        return

    cfg.enabled = True
    cfg.sent = 0
    cfg.task = asyncio.create_task(activity_loop(cid))

    log(f"🟢 Activity ENABLED | channel_id={cid}")
    await msg.answer("🟢 Запущено")

@router.message(Command("stop_activity"))
async def stop_activity(msg: Message):
    cid = selected_channel(msg.from_user.id)
    if not cid:
        return

    cfg = channels[cid]
    cfg.enabled = False
    if cfg.task:
        cfg.task.cancel()

    log(f"🔴 Activity STOPPED | channel_id={cid}")
    await msg.answer("🔴 Остановлено")

@router.message(Command("status"))
async def status_cmd(msg: Message):
    cid = selected_channel(msg.from_user.id)
    if not cid:
        await msg.answer("Канал не выбран")
        return

    cfg = channels[cid]
    await msg.answer(
        f"📊 Статус:\n"
        f"Интервал: {cfg.interval} мин\n"
        f"Лимит: {cfg.limit}\n"
        f"Отправлено: {cfg.sent}\n"
        f"Активно: {'🟢' if cfg.enabled else '🔴'}"
    )

# ================= ЗАПУСК =====================

async def main():
    log("🚀 BOT STARTED")
    await dp.start_polling(
        bot,
        allowed_updates=["my_chat_member", "message"]
    )

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import subprocess
import sys
import os

def install_packages():
    required_packages = [
        "aiogram>=3.0.0",
        "aiohttp>=3.8.0",
        "python-dotenv>=1.0.0",
        "fragment-api-lib>=1.0.0",
    ]
    for package in required_packages:
        package_name = package.split(">=")[0]
        try:
            __import__(package_name.replace("-", "_"))
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--break-system-packages"])

install_packages()

import sqlite3
import uuid
from datetime import datetime
from typing import Optional
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  Конфиг
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
MARKUP_PERCENT = int(os.getenv("MARKUP_PERCENT", 20))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "support")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
TON_SEED = os.getenv("TON_SEED")
DB_PATH = "stars_bot.db"

CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_BANK = os.getenv("CARD_BANK", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
CARD_PHONE = os.getenv("CARD_PHONE", "")

REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "-1003304197671")
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK", "https://t.me/HollywoodStarsChannel")

TON_RUB = 105.45
STARS_TON_PRICE = 0.010749
STAR_SELL_PRICE = 0.0
LAST_UPDATE_TIME = None

PREMIUM_PACKAGES = [
    {"months": 3,  "price_ton": 8.30,  "price_rub": 0},
    {"months": 6,  "price_ton": 11.07, "price_rub": 0},
    {"months": 12, "price_ton": 20.07, "price_rub": 0},
]

# ═══════════════════════════════════════════════════════════════
#  Fragment API — исправленная инициализация
# ═══════════════════════════════════════════════════════════════

fragment_client = None
FRAGMENT_AVAILABLE = False

try:
    from fragment_api_lib.client import FragmentAPIClient
    FRAGMENT_AVAILABLE = True
except ImportError:
    FRAGMENT_AVAILABLE = False
    logging.warning("fragment_api_lib не установлен")

def init_fragment_client():
    global fragment_client
    if not FRAGMENT_AVAILABLE:
        logging.warning("Fragment API недоступен")
        return False
    if not TON_SEED:
        logging.warning("TON_SEED не задан в .env")
        return False
    # Валидация seed
    words = TON_SEED.strip().split()
    if len(words) not in [12, 24]:
        logging.error(f"TON_SEED должен быть 12 или 24 слов, получено: {len(words)}")
        return False
    try:
        fragment_client = FragmentAPIClient(seed=TON_SEED.strip())
        # Проверяем связь
        ping = fragment_client.ping()
        logging.info(f"Fragment клиент инициализирован. Ping: {ping}")
        return True
    except Exception as e:
        logging.error(f"Ошибка инициализации Fragment: {e}")
        fragment_client = None
        return False

# ═══════════════════════════════════════════════════════════════
#  Парсер курсов
# ═══════════════════════════════════════════════════════════════

async def fetch_ton_rub() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "rub"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["the-open-network"]["rub"])
    except Exception as e:
        logging.warning(f"fetch_ton_rub error: {e}")
    return TON_RUB

async def fetch_stars_ton_price() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://fragment.com/api/v1/stars/price",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("price_per_star", 0.010749))
    except:
        pass
    return STARS_TON_PRICE

async def update_prices():
    global TON_RUB, STARS_TON_PRICE, STAR_SELL_PRICE, LAST_UPDATE_TIME
    TON_RUB = await fetch_ton_rub()
    STARS_TON_PRICE = await fetch_stars_ton_price()
    STAR_SELL_PRICE = round(TON_RUB * STARS_TON_PRICE * (1 + MARKUP_PERCENT / 100), 2)
    for p in PREMIUM_PACKAGES:
        p["price_rub"] = round(p["price_ton"] * TON_RUB * (1 + MARKUP_PERCENT / 100), 0)
    LAST_UPDATE_TIME = datetime.now().strftime("%H:%M:%S")
    logging.info(f"Курсы: TON={TON_RUB:.2f}₽, Star={STAR_SELL_PRICE:.2f}₽")

async def price_updater_loop():
    while True:
        await asyncio.sleep(300)
        await update_prices()

def get_star_price(stars: int) -> float:
    return round(stars * STAR_SELL_PRICE, 2)

def get_star_packages():
    return [
        {"stars": 50,   "price": get_star_price(50)},
        {"stars": 100,  "price": get_star_price(100)},
        {"stars": 250,  "price": get_star_price(250)},
        {"stars": 500,  "price": get_star_price(500)},
        {"stars": 1000, "price": get_star_price(1000)},
        {"stars": 2500, "price": get_star_price(2500)},
        {"stars": 5000, "price": get_star_price(5000)},
    ]

# ═══════════════════════════════════════════════════════════════
#  База данных
# ═══════════════════════════════════════════════════════════════

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    with db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                balance REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
                amount_rub REAL NOT NULL,
                recipient TEXT DEFAULT '',
                payment_method TEXT DEFAULT '',
                payment_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                transaction_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS card_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_type TEXT NOT NULL,
                photo_file_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS stars_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                caption TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1
            );
        """)

def db_add_user(uid, username, full_name):
    with db_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?,?,?)", (uid, username, full_name))

def db_get_user(uid) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

def db_get_all_users():
    with db_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]

def db_get_balance(uid) -> float:
    u = db_get_user(uid)
    return round(u["balance"], 2) if u else 0.0

def db_add_balance(uid, amount):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))

def db_deduct_balance(uid, amount):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, uid))

def db_create_order(uid, otype, qty, amount, recipient) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (user_id, type, quantity, amount_rub, recipient) VALUES (?,?,?,?,?)",
            (uid, otype, qty, amount, recipient)
        )
        return cur.lastrowid

def db_get_order(order_id) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

def db_update_order(order_id, status, method="", tx_id=""):
    with db_conn() as conn:
        if method and tx_id:
            conn.execute("UPDATE orders SET status=?, payment_method=?, transaction_id=? WHERE id=?",
                         (status, method, tx_id, order_id))
        elif method:
            conn.execute("UPDATE orders SET status=?, payment_method=? WHERE id=?",
                         (status, method, order_id))
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

def db_create_card_payment(user_id, order_id, amount, payment_type, photo_file_id) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO card_payments (user_id, order_id, amount, payment_type, photo_file_id) VALUES (?,?,?,?,?)",
            (user_id, order_id, amount, payment_type, photo_file_id)
        )
        return cur.lastrowid

def db_get_card_payment(payment_id) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM card_payments WHERE id=?", (payment_id,)).fetchone()
        return dict(row) if row else None

def db_get_pending_card_payments():
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM card_payments WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()]

def db_update_card_payment(payment_id, status):
    with db_conn() as conn:
        conn.execute("UPDATE card_payments SET status=? WHERE id=?", (status, payment_id))

def db_user_orders(uid, limit=10):
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit)
        ).fetchall()]

def db_stats():
    with db_conn() as conn:
        return {
            "users":     conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "orders":    conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "completed": conn.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0],
            "failed":    conn.execute("SELECT COUNT(*) FROM orders WHERE status='failed'").fetchone()[0],
            "revenue":   round(conn.execute("SELECT COALESCE(SUM(amount_rub),0) FROM orders WHERE status='completed'").fetchone()[0], 2),
        }

def db_get_active_stars_photos():
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM stars_photos WHERE is_active=1 AND file_id != '' ORDER BY id"
        ).fetchall()]

def db_add_stars_photo(file_id, caption):
    with db_conn() as conn:
        conn.execute("INSERT INTO stars_photos (file_id, caption) VALUES (?,?)", (file_id, caption))

def db_delete_stars_photo(photo_id):
    with db_conn() as conn:
        conn.execute("DELETE FROM stars_photos WHERE id=?", (photo_id,))

def db_toggle_stars_photo(photo_id, is_active):
    with db_conn() as conn:
        conn.execute("UPDATE stars_photos SET is_active=? WHERE id=?", (is_active, photo_id))

def db_get_all_stars_photos():
    with db_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM stars_photos ORDER BY id").fetchall()]

# ═══════════════════════════════════════════════════════════════
#  CryptoBot
# ═══════════════════════════════════════════════════════════════

async def create_crypto_invoice(amount_rub: float) -> Optional[dict]:
    try:
        ton_amount = round(amount_rub / TON_RUB, 4)
        if ton_amount < 0.5:
            ton_amount = 0.5
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/createInvoice",
                json={"asset": "TON", "amount": str(ton_amount), "description": "Оплата заказа"},
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return {
                        "invoice_id": data["result"]["invoice_id"],
                        "pay_url": data["result"]["pay_url"]
                    }
    except Exception as e:
        logging.error(f"CryptoBot error: {e}")
    return None

async def check_crypto_payment(invoice_id: int) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/getInvoices",
                json={"invoice_ids": [invoice_id]},
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                if data.get("ok") and data["result"]["items"]:
                    return data["result"]["items"][0]["status"]
    except:
        pass
    return "unknown"

# ═══════════════════════════════════════════════════════════════
#  Fragment — ИСПРАВЛЕННЫЕ функции доставки (РАБОТАЕТ БЕЗ КУК)
# ═══════════════════════════════════════════════════════════════

async def send_stars_via_fragment(username: str, amount: int) -> dict:
    """Покупает Stars и отправляет пользователю через Fragment API (без KYC)."""
    if not FRAGMENT_AVAILABLE:
        raise Exception("Библиотека fragment-api-lib не установлена")
    if not fragment_client:
        raise Exception("Fragment клиент не инициализирован. Проверьте TON_SEED в .env")
    if amount < 50:
        raise Exception("Минимальное количество звезд — 50")
    if not TON_SEED:
        raise Exception("TON_SEED не задан в .env")

    clean_username = username.lstrip("@").strip()
    if not clean_username:
        raise Exception("Некорректный username получателя")

    def _do_buy():
        # buy_stars_without_kyc — работает без кук, нужен только seed
        result = fragment_client.buy_stars_without_kyc(
            username=clean_username,
            amount=amount,
            seed=TON_SEED  # ← ЯВНО передаём сид-фразу!
        )
        return result

    try:
        result = await asyncio.to_thread(_do_buy)
        tx_id = (
            result.get("transaction_id")
            or result.get("order_id")
            or result.get("id")
            or f"stars_{uuid.uuid4().hex[:12]}"
        )
        logging.info(f"Stars отправлены: {amount} → @{clean_username}, tx={tx_id}")
        return {"success": True, "transaction_id": str(tx_id)}
    except Exception as e:
        err = str(e)
        logging.error(f"send_stars_via_fragment error: {err}")
        raise Exception(f"Ошибка Fragment API: {err}")


async def send_premium_via_fragment(username: str, months: int) -> dict:
    """Покупает Telegram Premium через Fragment API (без KYC)."""
    if not FRAGMENT_AVAILABLE:
        raise Exception("Библиотека fragment-api-lib не установлена")
    if not fragment_client:
        raise Exception("Fragment клиент не инициализирован. Проверьте TON_SEED в .env")
    if months not in [3, 6, 12]:
        raise Exception(f"Недопустимый срок Premium: {months} мес. Доступно: 3, 6, 12")
    if not TON_SEED:
        raise Exception("TON_SEED не задан в .env")

    clean_username = username.lstrip("@").strip()
    if not clean_username:
        raise Exception("Некорректный username получателя")

    def _do_buy():
        # buy_premium_without_kyc — работает без кук, нужен seed
        result = fragment_client.buy_premium_without_kyc(
            username=clean_username,
            duration=months,
            seed=TON_SEED  # ← ЯВНО передаём сид-фразу!
        )
        return result

    try:
        result = await asyncio.to_thread(_do_buy)
        tx_id = (
            result.get("transaction_id")
            or result.get("order_id")
            or result.get("id")
            or f"premium_{uuid.uuid4().hex[:12]}"
        )
        logging.info(f"Premium отправлен: {months}мес → @{clean_username}, tx={tx_id}")
        return {"success": True, "transaction_id": str(tx_id)}
    except Exception as e:
        err = str(e)
        logging.error(f"send_premium_via_fragment error: {err}")
        raise Exception(f"Ошибка Fragment API: {err}")

# ═══════════════════════════════════════════════════════════════
#  FSM
# ═══════════════════════════════════════════════════════════════

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class AddBalanceState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()

class BuyStars(StatesGroup):
    choose_recipient = State()
    enter_username = State()
    choose_package = State()

class TopUpState(StatesGroup):
    waiting_for_amount = State()

class CardPaymentState(StatesGroup):
    waiting_for_screenshot = State()

class AdminAddPhotoState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_caption = State()

# ═══════════════════════════════════════════════════════════════
#  Bot & Dispatcher
# ═══════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════════════════════════
#  Клавиатуры — с премиум эмодзи
# ═══════════════════════════════════════════════════════════════

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=" Купить Stars",
            callback_data="menu_buy_stars",
            icon_custom_emoji_id="5870930636742595124"
        )],
        [InlineKeyboardButton(
            text=" Купить Premium",
            callback_data="menu_buy_premium",
            icon_custom_emoji_id="6032644646587338669"
        )],
        [InlineKeyboardButton(
            text="Мой профиль",
            callback_data="menu_profile",
            icon_custom_emoji_id="5870994129244131212"
        )],
        [
            InlineKeyboardButton(
                text="Мои заказы",
                callback_data="menu_orders",
                icon_custom_emoji_id="5884479287171485878"
            ),
            InlineKeyboardButton(
                text="Поддержка",
                callback_data="menu_help",
                icon_custom_emoji_id="6028435952299413210"
            ),
        ],
    ])

def recipient_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Себе",
            callback_data="rec_self",
            icon_custom_emoji_id="5870994129244131212"
        )],
        [InlineKeyboardButton(
            text="Другу",
            callback_data="rec_friend",
            icon_custom_emoji_id="6032644646587338669"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_main",
            icon_custom_emoji_id="5893057118545646106"
        )],
    ])

def stars_packages_keyboard(username: str):
    kb = []
    for p in get_star_packages():
        kb.append([InlineKeyboardButton(
            text=f"⭐ {p['stars']} звезд — {p['price']}₽",
            callback_data=f"stars_{p['stars']}_{username}",
            icon_custom_emoji_id="5870930636742595124"
        )])
    kb.append([InlineKeyboardButton(
        text="Своё число",
        callback_data=f"stars_custom_{username}",
        icon_custom_emoji_id="5870676941614354370"
    )])
    kb.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5893057118545646106"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def payment_keyboard(order_id: int, amount: float, balance: float):
    kb = []
    if balance >= amount:
        kb.append([InlineKeyboardButton(
            text=f"Списать с баланса ({balance}₽)",
            callback_data=f"pay_balance_{order_id}",
            icon_custom_emoji_id="5769126056262898415"
        )])
    kb.append([InlineKeyboardButton(
        text="Оплата картой",
        callback_data=f"pay_card_{order_id}",
        icon_custom_emoji_id="5904462880941545555"
    )])
    kb.append([InlineKeyboardButton(
        text="CryptoBot (TON)",
        callback_data=f"pay_crypto_{order_id}",
        icon_custom_emoji_id="5260752406890711732"
    )])
    kb.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5893057118545646106"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def premium_keyboard():
    kb = []
    for p in PREMIUM_PACKAGES:
        kb.append([InlineKeyboardButton(
            text=f"💎 {p['months']} мес — {int(p['price_rub'])}₽",
            callback_data=f"premium_{p['months']}",
            icon_custom_emoji_id="6032644646587338669"
        )])
    kb.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5893057118545646106"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Статистика",
            callback_data="admin_stats",
            icon_custom_emoji_id="5870921681735781843"
        )],
        [InlineKeyboardButton(
            text="Рассылка",
            callback_data="admin_broadcast",
            icon_custom_emoji_id="6039422865189638057"
        )],
        [InlineKeyboardButton(
            text="Добавить баланс",
            callback_data="admin_add_balance",
            icon_custom_emoji_id="5769126056262898415"
        )],
        [InlineKeyboardButton(
            text="Управление фото",
            callback_data="admin_photos",
            icon_custom_emoji_id="6035128606563241721"
        )],
        [InlineKeyboardButton(
            text="Платежи по карте",
            callback_data="admin_card_payments",
            icon_custom_emoji_id="5904462880941545555"
        )],
    ])

def admin_photos_keyboard():
    photos = db_get_all_stars_photos()
    kb = []
    for p in photos:
        if p["file_id"]:
            status = "✅" if p["is_active"] else "❌"
            kb.append([InlineKeyboardButton(
                text=f"{status} Фото #{p['id']}",
                callback_data=f"photo_toggle_{p['id']}",
                icon_custom_emoji_id="6035128606563241721"
            )])
            kb.append([InlineKeyboardButton(
                text=f"Удалить #{p['id']}",
                callback_data=f"photo_delete_{p['id']}",
                icon_custom_emoji_id="5870875489362513438"
            )])
    kb.append([InlineKeyboardButton(
        text="Добавить фото",
        callback_data="photo_add",
        icon_custom_emoji_id="6035128606563241721"
    )])
    kb.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_admin",
        icon_custom_emoji_id="5893057118545646106"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Пополнить баланс",
            callback_data="topup_menu",
            icon_custom_emoji_id="5879814368572478751"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_main",
            icon_custom_emoji_id="5893057118545646106"
        )],
    ])

def topup_method_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Карта",
            callback_data="topup_card",
            icon_custom_emoji_id="5904462880941545555"
        )],
        [InlineKeyboardButton(
            text="CryptoBot (TON)",
            callback_data="topup_crypto",
            icon_custom_emoji_id="5260752406890711732"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_main",
            icon_custom_emoji_id="5893057118545646106"
        )],
    ])

def admin_payments_keyboard():
    payments = db_get_pending_card_payments()
    kb = []
    for p in payments:
        type_text = "Пополнение" if p["payment_type"] == "topup" else "Покупка"
        kb.append([InlineKeyboardButton(
            text=f"{type_text} #{p['id']} | {p['amount']}₽",
            callback_data=f"view_payment_{p['id']}",
            icon_custom_emoji_id="5904462880941545555"
        )])
    kb.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_admin",
        icon_custom_emoji_id="5893057118545646106"
    )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def payment_action_keyboard(payment_id: int, payment_type: str):
    if payment_type == "topup":
        approve_cb = f"approve_topup_{payment_id}"
        approve_text = "Одобрить пополнение"
    else:
        approve_cb = f"approve_purchase_{payment_id}"
        approve_text = "Одобрить покупку"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=approve_text,
            callback_data=approve_cb,
            icon_custom_emoji_id="5870633910337015697"
        )],
        [InlineKeyboardButton(
            text="Отклонить",
            callback_data=f"reject_payment_{payment_id}",
            icon_custom_emoji_id="5870657884844462243"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="admin_card_payments",
            icon_custom_emoji_id="5893057118545646106"
        )],
    ])

# ═══════════════════════════════════════════════════════════════
#  Вспомогательные функции
# ═══════════════════════════════════════════════════════════════

def sub_required_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Подписаться на канал",
            url=REQUIRED_CHANNEL_LINK,
            icon_custom_emoji_id="6039422865189638057"
        )],
        [InlineKeyboardButton(
            text="Проверить подписку",
            callback_data="check_subscription",
            icon_custom_emoji_id="5870633910337015697"
        )],
    ])

SUB_REQUIRED_TEXT = (
    '<b><tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Доступ запрещён!</b>\n\n'
    'Для использования бота необходимо подписаться на наш канал:\n'
    f'👉 <a href="{REQUIRED_CHANNEL_LINK}">HollywoodStars Channel</a>\n\n'
    '<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> После подписки нажмите кнопку ниже:'
)

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"check_subscription({user_id}): {e}")
        return False

async def require_sub_cb(cb: CallbackQuery) -> bool:
    """Возвращает False и показывает заглушку, если пользователь не подписан."""
    if await check_subscription(cb.from_user.id):
        return True
    try:
        await cb.message.edit_text(SUB_REQUIRED_TEXT, reply_markup=sub_required_kb(), disable_web_page_preview=True)
    except:
        await cb.message.answer(SUB_REQUIRED_TEXT, reply_markup=sub_required_kb(), disable_web_page_preview=True)
    await cb.answer()
    return False

async def require_sub_msg(msg: Message) -> bool:
    if await check_subscription(msg.from_user.id):
        return True
    await msg.answer(SUB_REQUIRED_TEXT, reply_markup=sub_required_kb(), disable_web_page_preview=True)
    return False

async def send_welcome(target, reply_markup):
    """Отправляет приветственное сообщение с фото или без."""
    photos = db_get_active_stars_photos()
    caption = (
        '<b><tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Добро пожаловать в HollywoodStars!</b>\n\n'
        '<tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> Здесь вы можете приобрести <b>Telegram Stars</b> и\n'
        '<b>Telegram Premium</b> на свой аккаунт за рубли\n\n'
        f'<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Обновлён: {LAST_UPDATE_TIME}\n\n'
        '<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>Хороших покупок!</b>'
    )
    if photos and photos[0]["file_id"]:
        if isinstance(target, Message):
            await target.answer_photo(photo=photos[0]["file_id"], caption=caption, reply_markup=reply_markup)
        else:
            await target.answer_photo(photo=photos[0]["file_id"], caption=caption, reply_markup=reply_markup)
    else:
        if isinstance(target, Message):
            await target.answer(caption, reply_markup=reply_markup)
        else:
            await target.answer(caption, reply_markup=reply_markup)

# ═══════════════════════════════════════════════════════════════
#  Обработчики
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(cb: CallbackQuery):
    if not await check_subscription(cb.from_user.id):
        await cb.answer(
            "❌ Вы ещё не подписаны на канал! Подпишитесь и нажмите «Проверить подписку»",
            show_alert=True
        )
        return
    db_add_user(cb.from_user.id, cb.from_user.username or "", cb.from_user.full_name)
    await update_prices()
    try:
        await cb.message.delete()
    except:
        pass
    await send_welcome(cb.message, main_menu_keyboard())
    await cb.answer()

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    if not await check_subscription(msg.from_user.id):
        await msg.answer(SUB_REQUIRED_TEXT, reply_markup=sub_required_kb(), disable_web_page_preview=True)
        return
    db_add_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.full_name)
    await update_prices()
    await send_welcome(msg, main_menu_keyboard())

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    await state.clear()
    await update_prices()
    try:
        await cb.message.delete()
    except:
        pass
    await send_welcome(cb.message, main_menu_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_profile")
async def menu_profile(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    user = db_get_user(cb.from_user.id)
    orders = db_user_orders(cb.from_user.id)
    completed = [o for o in orders if o["status"] == "completed"]
    total_spent = sum(o["amount_rub"] for o in completed)

    text = (
        '<b><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Профиль</b>\n\n'
        f'🆔 Id: <code>{cb.from_user.id}</code>\n'
        f'👤 Username: @{cb.from_user.username or "не указан"}\n'
        f'📅 Регистрация: {user["created_at"][:10]}\n\n'
        f'<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Баланс: <b>{user["balance"]}₽</b>\n'
        f'💵 Потрачено: {total_spent}₽\n'
        f'🔢 Покупок: {len(completed)}\n\n'
        f'<tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> 1 Star = {STAR_SELL_PRICE:.2f}₽\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Курс: {LAST_UPDATE_TIME}'
    )
    try:
        await cb.message.edit_text(text, reply_markup=profile_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=profile_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_buy_stars")
async def menu_buy_stars(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    await state.set_state(BuyStars.choose_recipient)
    text = (
        '<b><tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> Покупка Stars</b>\n\n'
        f'<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> 1 Star = {STAR_SELL_PRICE:.2f}₽\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Курс: {LAST_UPDATE_TIME}\n\n'
        '<b>Кому отправить звёзды?</b>'
    )
    try:
        await cb.message.edit_text(text, reply_markup=recipient_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=recipient_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_buy_premium")
async def menu_buy_premium(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    text = (
        '<b><tg-emoji emoji-id="6032644646587338669">💎</tg-emoji> Telegram Premium</b>\n\n'
        f'<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> 1 TON = {TON_RUB:.2f}₽\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Курс: {LAST_UPDATE_TIME}\n\n'
        'Выберите срок подписки:'
    )
    try:
        await cb.message.edit_text(text, reply_markup=premium_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=premium_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_orders")
async def menu_orders(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    orders = db_user_orders(cb.from_user.id, limit=10)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5893057118545646106"
    )]])
    if not orders:
        text = '<b><tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Мои заказы</b>\n\n❌ У вас пока нет заказов.'
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
        return

    status_emoji = {"completed": "✅", "processing": "🔄", "pending": "⏳", "failed": "❌", "cancelled": "❌"}
    text = '<b><tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Мои заказы</b>\n\n'
    for o in orders:
        em = status_emoji.get(o["status"], "❓")
        product = "Premium" if o["type"] == "premium" else "Stars" if o["type"] == "stars" else "Пополнение"
        text += f'{em} <b>#{o["id"]}</b> | {product}\n💰 {o["amount_rub"]}₽\n📅 {o["created_at"][:16]}\n\n'

    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "menu_help")
async def menu_help(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    text = (
        '<b><tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji> Помощь</b>\n\n'
        '1️⃣ Нажмите «Купить Stars»\n'
        '2️⃣ Выберите получателя (себе или другу)\n'
        '3️⃣ Выберите количество звёзд\n'
        '4️⃣ Оплатите удобным способом\n\n'
        '<b>Способы оплаты:</b>\n'
        '• Списать с баланса\n'
        '• Карта\n'
        '• CryptoBot (TON)\n\n'
        '<b>Пополнить баланс:</b>\n'
        '• Мой профиль → Пополнить баланс\n\n'
        f'<tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> 1 Star = {STAR_SELL_PRICE:.2f}₽\n'
        f'<tg-emoji emoji-id="6032644646587338669">💎</tg-emoji> Premium 3 мес = {int(PREMIUM_PACKAGES[0]["price_rub"])}₽\n\n'
        f'<tg-emoji emoji-id="6039422865189638057">📣</tg-emoji> <b>Поддержка:</b> @{SUPPORT_USERNAME}'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "topup_menu")
async def topup_menu(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    text = '<b><tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Пополнение баланса</b>\n\nВыберите способ:'
    try:
        await cb.message.edit_text(text, reply_markup=topup_method_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=topup_method_keyboard())
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Покупка Stars
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "rec_self")
async def rec_self(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    username = cb.from_user.username or str(cb.from_user.id)
    await state.update_data(recipient=username)
    await state.set_state(BuyStars.choose_package)
    text = (
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Получатель: @{username}\n\n'
        '<b>⭐ Выберите количество:</b>'
    )
    try:
        await cb.message.edit_text(text, reply_markup=stars_packages_keyboard(username))
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=stars_packages_keyboard(username))
    await cb.answer()

@dp.callback_query(F.data == "rec_friend")
async def rec_friend(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    text = (
        '<b><tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji> Покупка другу</b>\n\n'
        'Введите <b>username</b> получателя (без @):'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await state.set_state(BuyStars.enter_username)
    await cb.answer()

@dp.message(BuyStars.enter_username)
async def friend_username(msg: Message, state: FSMContext):
    if not await require_sub_msg(msg):
        return
    username = msg.text.strip().lstrip("@")
    if not username:
        await msg.answer("❌ Введите корректный username!")
        return
    await state.update_data(recipient=username)
    await state.set_state(BuyStars.choose_package)
    text = (
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Получатель: @{username}\n\n'
        '<b>⭐ Выберите количество:</b>'
    )
    await msg.answer(text, reply_markup=stars_packages_keyboard(username))

@dp.callback_query(F.data.startswith("stars_"))
async def choose_stars_package(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    parts = cb.data.split("_")

    if parts[1] == "custom":
        text = '✏️ <b>Введите количество звёзд</b>\n\nОт 50 до 1 000 000:'
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5893057118545646106"
        )]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
        await state.set_state(BuyStars.choose_package)
        await cb.answer()
        return

    stars = int(parts[1])
    data = await state.get_data()
    username = data.get("recipient") or (cb.from_user.username or str(cb.from_user.id))
    amount = get_star_price(stars)
    balance = db_get_balance(cb.from_user.id)
    order_id = db_create_order(cb.from_user.id, "stars", stars, amount, username)
    await state.update_data(order_id=order_id, stars=stars, username=username, amount=amount)

    text = (
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Покупка {stars} звёзд</b>\n\n'
        f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Получатель: @{username}\n'
        f'<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Сумма: <b>{amount}₽</b>\n'
        f'🆔 Id заказа: <code>{order_id}</code>\n\n'
        f'Ваш баланс: <b>{balance}₽</b>\n\n'
        '<b>Выберите способ оплаты:</b>'
    )
    try:
        await cb.message.edit_text(text, reply_markup=payment_keyboard(order_id, amount, balance))
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=payment_keyboard(order_id, amount, balance))
    await cb.answer()

@dp.message(BuyStars.choose_package)
async def custom_stars(msg: Message, state: FSMContext):
    if not await require_sub_msg(msg):
        return
    try:
        stars = int(msg.text.strip())
        if stars < 50 or stars > 1_000_000:
            raise ValueError
    except:
        await msg.answer("❌ Введите число от 50 до 1 000 000!")
        return

    data = await state.get_data()
    username = data.get("recipient") or (msg.from_user.username or str(msg.from_user.id))
    amount = get_star_price(stars)
    balance = db_get_balance(msg.from_user.id)
    order_id = db_create_order(msg.from_user.id, "stars", stars, amount, username)
    await state.update_data(order_id=order_id, stars=stars, username=username, amount=amount)

    text = (
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Покупка {stars} звёзд</b>\n\n'
        f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Получатель: @{username}\n'
        f'<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Сумма: <b>{amount}₽</b>\n'
        f'🆔 Id заказа: <code>{order_id}</code>\n\n'
        f'Ваш баланс: <b>{balance}₽</b>\n\n'
        '<b>Выберите способ оплаты:</b>'
    )
    await msg.answer(text, reply_markup=payment_keyboard(order_id, amount, balance))

# ═══════════════════════════════════════════════════════════════
#  Premium
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("premium_"))
async def choose_premium(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    months = int(cb.data.split("_")[1])
    pkg = next(p for p in PREMIUM_PACKAGES if p["months"] == months)
    username = cb.from_user.username or str(cb.from_user.id)
    amount = pkg["price_rub"]
    balance = db_get_balance(cb.from_user.id)
    order_id = db_create_order(cb.from_user.id, "premium", months, amount, username)
    await state.update_data(order_id=order_id, months=months, username=username, amount=amount)

    text = (
        f'<tg-emoji emoji-id="6032644646587338669">💎</tg-emoji> <b>Premium на {months} мес.</b>\n\n'
        f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Получатель: @{username}\n'
        f'<tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Сумма: <b>{amount}₽</b>\n'
        f'🆔 Id заказа: <code>{order_id}</code>\n\n'
        f'Ваш баланс: <b>{balance}₽</b>\n\n'
        '<b>Выберите способ оплаты:</b>'
    )
    try:
        await cb.message.edit_text(text, reply_markup=payment_keyboard(order_id, amount, balance))
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=payment_keyboard(order_id, amount, balance))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Доставка товара
# ═══════════════════════════════════════════════════════════════

async def deliver_order(order_id: int, user_id: int):
    order = db_get_order(order_id)
    if not order:
        raise Exception(f"Заказ #{order_id} не найден")

    if order["type"] == "stars":
        result = await send_stars_via_fragment(order["recipient"], order["quantity"])
        db_update_order(order_id, "completed", order["payment_method"], result["transaction_id"])
        await bot.send_message(
            user_id,
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Заказ #{order_id} выполнен!</b>\n\n'
            f'<tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> {order["quantity"]} звёзд отправлены @{order["recipient"]}\n\n'
            f'<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Спасибо за покупку!',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )]])
        )

    elif order["type"] == "premium":
        result = await send_premium_via_fragment(order["recipient"], order["quantity"])
        db_update_order(order_id, "completed", order["payment_method"], result["transaction_id"])
        await bot.send_message(
            user_id,
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Заказ #{order_id} выполнен!</b>\n\n'
            f'<tg-emoji emoji-id="6032644646587338669">💎</tg-emoji> Premium на {order["quantity"]} мес. активирован для @{order["recipient"]}\n\n'
            f'<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Спасибо за покупку!',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )]])
        )

# ═══════════════════════════════════════════════════════════════
#  Оплата с баланса
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_balance_"))
async def pay_balance(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return

    balance = db_get_balance(cb.from_user.id)
    if balance < order["amount_rub"]:
        await cb.answer(
            f"❌ Недостаточно средств! Нужно {order['amount_rub']}₽, у вас {balance}₽",
            show_alert=True
        )
        return

    db_deduct_balance(cb.from_user.id, order["amount_rub"])
    db_update_order(order_id, "processing", "balance")

    text = (
        f'<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji> <b>Заказ #{order_id} в обработке...</b>\n\n'
        f'<tg-emoji emoji-id="5890848474563352982">🪙</tg-emoji> Списано: {order["amount_rub"]}₽'
    )
    try:
        await cb.message.edit_text(text)
    except:
        await cb.message.delete()
        await cb.message.answer(text)

    try:
        await deliver_order(order_id, cb.from_user.id)
    except Exception as e:
        db_add_balance(cb.from_user.id, order["amount_rub"])
        db_update_order(order_id, "failed", "balance")
        err_text = (
            f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Ошибка выполнения заказа</b>\n\n'
            f'{str(e)}\n\n'
            f'Деньги возвращены на баланс.\n\n'
            f'Обратитесь в поддержку: @{SUPPORT_USERNAME}'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
        )]])
        try:
            await cb.message.edit_text(err_text, reply_markup=kb)
        except:
            await cb.message.answer(err_text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Оплата картой
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_card_"))
async def pay_card(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return
    if not CARD_NUMBER:
        await cb.answer("❌ Оплата картой временно недоступна", show_alert=True)
        return

    await state.update_data(card_order_id=order_id)
    await state.set_state(CardPaymentState.waiting_for_screenshot)

    if order["type"] == "topup":
        prod_text = "пополнение баланса"
    elif order["type"] == "stars":
        prod_text = f"покупку {order['quantity']} звёзд"
    else:
        prod_text = f"покупку Premium на {order['quantity']} мес"

    text = (
        f'<b><tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji> Оплата картой</b>\n\n'
        f'📦 Заказ #{order_id}\n'
        f'💰 Сумма: <b>{order["amount_rub"]}₽</b>\n'
        f'📝 Товар: {prod_text}\n\n'
        f'<b>Реквизиты:</b>\n'
        f'┌ Номер карты: <code>{CARD_NUMBER}</code>\n'
        f'├ Банк: {CARD_BANK}\n'
        f'├ Держатель: {CARD_HOLDER}\n'
        f'└ Телефон: {CARD_PHONE}\n\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> <b>После оплаты отправьте скриншот чека</b>\n\n'
        f'❗ На скриншоте должны быть видны:\n'
        f'• Сумма и дата\n'
        f'• Последние 4 цифры карты'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.message(CardPaymentState.waiting_for_screenshot)
async def handle_card_screenshot(msg: Message, state: FSMContext):
    if not await require_sub_msg(msg):
        return
    if not msg.photo:
        await msg.answer("❌ Пожалуйста, отправьте скриншот чека (фото)")
        return

    data = await state.get_data()
    order_id = data.get("card_order_id")
    if not order_id:
        await msg.answer("❌ Ошибка: данные не найдены. Начните оплату заново.")
        await state.clear()
        return

    order = db_get_order(order_id)
    if not order:
        await msg.answer("❌ Заказ не найден")
        await state.clear()
        return

    if order["type"] == "topup":
        payment_type = "topup"
        prod_text = "Пополнение баланса"
    elif order["type"] == "stars":
        payment_type = "purchase"
        prod_text = f"Покупка {order['quantity']} звёзд"
    else:
        payment_type = "purchase"
        prod_text = f"Покупка Premium на {order['quantity']} мес"

    photo_file_id = msg.photo[-1].file_id
    payment_id = db_create_card_payment(
        user_id=msg.from_user.id,
        order_id=order_id,
        amount=order["amount_rub"],
        payment_type=payment_type,
        photo_file_id=photo_file_id
    )
    db_update_order(order_id, "pending", "card")

    await msg.answer(
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Скриншот получен!</b>\n\n'
        f'📦 Заказ #{order_id}\n'
        f'💰 Сумма: {order["amount_rub"]}₽\n'
        f'📝 {prod_text}\n\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Ожидайте подтверждения администратора.\n\n'
        f'Статус: раздел «Мои заказы»',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
        )]])
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=photo_file_id,
                caption=(
                    f'<tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji> <b>Новый платёж по карте</b>\n\n'
                    f'👤 @{msg.from_user.username or msg.from_user.id}\n'
                    f'🆔 ID: {msg.from_user.id}\n'
                    f'📦 Заказ #{order_id}\n'
                    f'💰 Сумма: {order["amount_rub"]}₽\n'
                    f'📝 {prod_text}\n'
                    f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Получатель: @{order["recipient"]}\n'
                    f'📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                ),
                reply_markup=payment_action_keyboard(payment_id, payment_type)
            )
        except Exception as e:
            logging.error(f"Ошибка отправки админу {admin_id}: {e}")
    await state.clear()

# ═══════════════════════════════════════════════════════════════
#  Обработка платежей администратором
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("view_payment_"))
async def view_payment(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    if not payment:
        await cb.answer("Платёж не найден", show_alert=True)
        return
    order = db_get_order(payment["order_id"])
    await cb.answer()
    await cb.message.answer_photo(
        photo=payment["photo_file_id"],
        caption=(
            f'💳 <b>Платёж #{payment_id}</b>\n\n'
            f'👤 Пользователь: {payment["user_id"]}\n'
            f'📦 Заказ #{payment["order_id"]}\n'
            f'💰 Сумма: {payment["amount"]}₽\n'
            f'📝 Тип: {"Пополнение" if payment["payment_type"] == "topup" else "Покупка"}\n'
            f'👤 Получатель: @{order["recipient"]}\n'
            f'📅 {payment["created_at"]}'
        ),
        reply_markup=payment_action_keyboard(payment_id, payment["payment_type"])
    )

@dp.callback_query(F.data.startswith("approve_topup_"))
async def approve_topup(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    if not payment:
        await cb.answer("Платёж не найден", show_alert=True)
        return
    if payment["status"] != "pending":
        await cb.answer("Платёж уже обработан", show_alert=True)
        return

    db_update_card_payment(payment_id, "approved")
    db_update_order(payment["order_id"], "completed", "card")
    db_add_balance(payment["user_id"], payment["amount"])
    new_balance = db_get_balance(payment["user_id"])

    await cb.answer("✅ Пополнение одобрено!")
    try:
        await cb.message.delete()
    except:
        pass
    await cb.message.answer(
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Пополнение одобрено!</b>\n\n'
        f'👤 {payment["user_id"]}\n'
        f'💰 +{payment["amount"]}₽ → баланс: {new_balance}₽',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="К списку платежей", callback_data="admin_card_payments",
            icon_custom_emoji_id="5893057118545646106"
        )]])
    )
    try:
        await bot.send_message(
            payment["user_id"],
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Баланс пополнен!</b>\n\n'
            f'💰 +{payment["amount"]}₽\n'
            f'📊 Новый баланс: {new_balance}₽\n\n'
            f'<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Спасибо!',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )]])
        )
    except:
        pass

@dp.callback_query(F.data.startswith("approve_purchase_"))
async def approve_purchase(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    if not payment:
        await cb.answer("Платёж не найден", show_alert=True)
        return
    if payment["status"] != "pending":
        await cb.answer("Платёж уже обработан", show_alert=True)
        return

    db_update_card_payment(payment_id, "approved")
    db_update_order(payment["order_id"], "processing", "card")

    await cb.answer("✅ Покупка одобрена!")
    try:
        await cb.message.delete()
    except:
        pass
    await cb.message.answer(
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Покупка одобрена!</b>\n\n'
        f'📦 Заказ #{payment["order_id"]}\n'
        f'<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji> Отправляем товар...',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="К списку платежей", callback_data="admin_card_payments",
            icon_custom_emoji_id="5893057118545646106"
        )]])
    )

    try:
        await deliver_order(payment["order_id"], payment["user_id"])
    except Exception as e:
        db_update_order(payment["order_id"], "failed", "card")
        try:
            await bot.send_message(
                payment["user_id"],
                f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Ошибка выполнения заказа #{payment["order_id"]}</b>\n\n'
                f'{str(e)}\n\n'
                f'Обратитесь в поддержку: @{SUPPORT_USERNAME}',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
                )]])
            )
        except:
            pass
        logging.error(f"deliver_order failed for order {payment['order_id']}: {e}")

@dp.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    if not payment:
        await cb.answer("Платёж не найден", show_alert=True)
        return
    if payment["status"] != "pending":
        await cb.answer("Платёж уже обработан", show_alert=True)
        return

    db_update_card_payment(payment_id, "rejected")
    db_update_order(payment["order_id"], "failed", "card")

    await cb.answer("❌ Платёж отклонён!")
    try:
        await cb.message.delete()
    except:
        pass
    await cb.message.answer(
        f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Платёж отклонён</b>\n\n'
        f'📦 Заказ #{payment["order_id"]}\n'
        f'💰 {payment["amount"]}₽',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="К списку платежей", callback_data="admin_card_payments",
            icon_custom_emoji_id="5893057118545646106"
        )]])
    )
    type_text = "пополнение баланса" if payment["payment_type"] == "topup" else "покупка"
    try:
        await bot.send_message(
            payment["user_id"],
            f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Ваш платёж отклонён</b>\n\n'
            f'📝 Операция: {type_text}\n'
            f'💰 Сумма: {payment["amount"]}₽\n\n'
            f'Причина: неверный скриншот или сумма не совпадает\n\n'
            f'📞 Поддержка: @{SUPPORT_USERNAME}',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )]])
        )
    except:
        pass

# ═══════════════════════════════════════════════════════════════
#  Пополнение баланса
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "topup_card")
async def topup_card(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    await state.set_state(TopUpState.waiting_for_amount)
    await state.update_data(topup_method="card")
    text = '<b>💳 Пополнение картой</b>\n\nВведите сумму (от 100₽):'
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="topup_menu", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "topup_crypto")
async def topup_crypto_start(cb: CallbackQuery, state: FSMContext):
    if not await require_sub_cb(cb):
        return
    await state.set_state(TopUpState.waiting_for_amount)
    await state.update_data(topup_method="crypto")
    text = '<b><tg-emoji emoji-id="5260752406890711732">👾</tg-emoji> Пополнение через CryptoBot</b>\n\nВведите сумму (от 100₽):'
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="topup_menu", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.message(TopUpState.waiting_for_amount)
async def topup_amount(msg: Message, state: FSMContext):
    if not await require_sub_msg(msg):
        return
    try:
        amount = float(msg.text.strip())
        if amount < 100:
            raise ValueError
    except:
        await msg.answer("❌ Введите сумму от 100₽!")
        return

    data = await state.get_data()
    method = data.get("topup_method", "crypto")

    if method == "card":
        username = msg.from_user.username or str(msg.from_user.id)
        order_id = db_create_order(msg.from_user.id, "topup", 0, amount, username)
        await state.update_data(card_order_id=order_id)
        await state.set_state(CardPaymentState.waiting_for_screenshot)

        text = (
            f'<b><tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji> Пополнение картой</b>\n\n'
            f'💰 Сумма: <b>{amount}₽</b>\n'
            f'🆔 Операция: <code>{order_id}</code>\n\n'
            f'<b>Реквизиты:</b>\n'
            f'┌ Номер карты: <code>{CARD_NUMBER}</code>\n'
            f'├ Банк: {CARD_BANK}\n'
            f'├ Держатель: {CARD_HOLDER}\n'
            f'└ Телефон: {CARD_PHONE}\n\n'
            f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> Отправьте скриншот чека после оплаты'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Назад", callback_data="topup_menu", icon_custom_emoji_id="5893057118545646106"
        )]])
        await msg.answer(text, reply_markup=kb)
    else:
        invoice = await create_crypto_invoice(amount)
        if not invoice:
            await msg.answer("❌ Ошибка создания счёта. Попробуйте позже.")
            await state.clear()
            return
        ton_amount = round(amount / TON_RUB, 4)
        text = (
            f'<b><tg-emoji emoji-id="5260752406890711732">👾</tg-emoji> Пополнение через CryptoBot</b>\n\n'
            f'💰 Сумма: <b>{amount}₽</b>\n'
            f'💎 К оплате: <b>{ton_amount} TON</b>\n\n'
            f'🔗 <a href="{invoice["pay_url"]}">Оплатить в CryptoBot</a>\n\n'
            f'После оплаты нажмите «Проверить оплату»'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Проверить оплату",
                callback_data=f"check_topup_{invoice['invoice_id']}_{amount}",
                icon_custom_emoji_id="5345906554510012647"
            )],
            [InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )],
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await state.clear()

@dp.callback_query(F.data.startswith("check_topup_"))
async def check_topup(cb: CallbackQuery):
    parts = cb.data.split("_")
    # check_topup_{invoice_id}_{amount} → parts[2] и parts[3]
    if len(parts) < 4:
        await cb.answer("❌ Ошибка формата", show_alert=True)
        return
    invoice_id = int(parts[2])
    amount = float(parts[3])
    status = await check_crypto_payment(invoice_id)

    if status == "paid":
        db_add_balance(cb.from_user.id, amount)
        text = (
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Баланс пополнен!</b>\n\n'
            f'💰 +{amount}₽\n'
            f'📊 Новый баланс: {db_get_balance(cb.from_user.id)}₽'
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
        )]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
    elif status == "active":
        await cb.answer("⏳ Оплата ещё не получена", show_alert=True)
    else:
        await cb.answer("❌ Счёт не оплачен или истёк", show_alert=True)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Оплата CryptoBot для заказов
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(cb: CallbackQuery):
    if not await require_sub_cb(cb):
        return
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return

    invoice = await create_crypto_invoice(order["amount_rub"])
    if not invoice:
        await cb.answer("❌ Ошибка создания счёта", show_alert=True)
        return

    db_update_order(order_id, "pending", "cryptobot", str(invoice["invoice_id"]))
    ton_amount = round(order["amount_rub"] / TON_RUB, 4)

    text = (
        f'<b><tg-emoji emoji-id="5260752406890711732">👾</tg-emoji> Оплата через CryptoBot</b>\n\n'
        f'💰 Сумма: <b>{order["amount_rub"]}₽</b>\n'
        f'💎 К оплате: <b>{ton_amount} TON</b>\n'
        f'🆔 Заказ: <code>{order_id}</code>\n\n'
        f'🔗 <a href="{invoice["pay_url"]}">Оплатить в CryptoBot</a>\n\n'
        f'После оплаты нажмите «Проверить оплату»'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Проверить оплату",
            callback_data=f"check_crypto_{order_id}",
            icon_custom_emoji_id="5345906554510012647"
        )],
        [InlineKeyboardButton(
            text="Отменить",
            callback_data=f"cancel_{order_id}",
            icon_custom_emoji_id="5870657884844462243"
        )],
        [InlineKeyboardButton(
            text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
        )],
    ])
    try:
        await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await cb.answer()

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_payment_handler(cb: CallbackQuery):
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return
    if not order["payment_id"]:
        await cb.answer("Ошибка: счёт не найден", show_alert=True)
        return

    status = await check_crypto_payment(int(order["payment_id"]))
    if status == "paid":
        db_update_order(order_id, "processing", "cryptobot")
        text = (
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Оплата получена!</b>\n\n'
            f'<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji> Отправляем...'
        )
        try:
            await cb.message.edit_text(text)
        except:
            await cb.message.delete()
            await cb.message.answer(text)
        try:
            await deliver_order(order_id, cb.from_user.id)
        except Exception as e:
            db_update_order(order_id, "failed", "cryptobot")
            err_text = (
                f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Ошибка!</b>\n\n'
                f'{str(e)}\n\nОбратитесь в поддержку: @{SUPPORT_USERNAME}'
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
            )]])
            try:
                await cb.message.edit_text(err_text, reply_markup=kb)
            except:
                await cb.message.answer(err_text, reply_markup=kb)
    elif status == "active":
        await cb.answer("⏳ Оплата ещё не получена", show_alert=True)
    else:
        await cb.answer("❌ Счёт не оплачен или истёк", show_alert=True)
    await cb.answer()

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(cb: CallbackQuery):
    order_id = int(cb.data.split("_")[1])
    db_update_order(order_id, "cancelled")
    text = f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Заказ #{order_id} отменён.'
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Главное меню", callback_data="back_to_main", icon_custom_emoji_id="5873147866364514353"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Админ-панель
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "admin_card_payments")
async def admin_card_payments(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    payments = db_get_pending_card_payments()
    if not payments:
        text = '<b>💳 Платежи по карте</b>\n\nНет неподтверждённых платежей'
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Назад", callback_data="back_to_admin", icon_custom_emoji_id="5893057118545646106"
        )]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
    else:
        text = '<b>💳 Платежи по карте</b>\n\n'
        for p in payments:
            type_text = "Пополнение" if p["payment_type"] == "topup" else "Покупка"
            text += f'#{p["id"]} | {type_text} | {p["amount"]}₽ | {p["created_at"][:16]}\n'
        try:
            await cb.message.edit_text(text, reply_markup=admin_payments_keyboard())
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=admin_payments_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "admin_photos")
async def admin_photos(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    photos = db_get_all_stars_photos()
    text = '<b><tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> Управление фото Stars</b>\n\n'
    if photos:
        for p in photos:
            if p["file_id"]:
                status = "✅ активное" if p["is_active"] else "❌ неактивное"
                caption_preview = (p["caption"] or "без подписи")[:50]
                text += f'#{p["id"]}: {status} — {caption_preview}\n'
    else:
        text += 'Нет добавленных фото'
    try:
        await cb.message.edit_text(text, reply_markup=admin_photos_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=admin_photos_keyboard())
    await cb.answer()

@dp.callback_query(F.data.startswith("photo_toggle_"))
async def photo_toggle(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    photo_id = int(cb.data.split("_")[2])
    photos = db_get_all_stars_photos()
    current = next((p for p in photos if p["id"] == photo_id), None)
    if current:
        new_status = 0 if current["is_active"] else 1
        db_toggle_stars_photo(photo_id, new_status)
        await cb.answer(f'Фото #{photo_id} {"активировано" if new_status else "деактивировано"}')
    await admin_photos(cb)

@dp.callback_query(F.data.startswith("photo_delete_"))
async def photo_delete(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    photo_id = int(cb.data.split("_")[2])
    db_delete_stars_photo(photo_id)
    await cb.answer(f"Фото #{photo_id} удалено")
    await admin_photos(cb)

@dp.callback_query(F.data == "photo_add")
async def photo_add(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminAddPhotoState.waiting_for_photo)
    text = '<b>Добавление фото</b>\n\nОтправьте фото для главного меню:'
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Назад", callback_data="admin_photos", icon_custom_emoji_id="5893057118545646106"
    )]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.message(AdminAddPhotoState.waiting_for_photo)
async def add_photo_receive(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not msg.photo:
        await msg.answer("❌ Отправьте фото")
        return
    file_id = msg.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await state.set_state(AdminAddPhotoState.waiting_for_caption)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Пропустить", callback_data="skip_caption", icon_custom_emoji_id="5893057118545646106"
    )]])
    await msg.answer("📝 Отправьте подпись (или нажмите «Пропустить»):", reply_markup=kb)

@dp.callback_query(F.data == "skip_caption")
async def skip_caption(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    db_add_stars_photo(data["photo_file_id"], "")
    await state.clear()
    await cb.message.answer("✅ Фото добавлено!")
    await admin_photos(cb)
    await cb.answer()

@dp.message(AdminAddPhotoState.waiting_for_caption)
async def add_photo_caption(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    db_add_stars_photo(data["photo_file_id"], msg.text or "")
    await state.clear()
    await msg.answer("✅ Фото добавлено!")

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    await _show_admin_panel(cb.message, edit=True)
    await cb.answer()

@dp.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await _show_admin_panel(msg, edit=False)

async def _show_admin_panel(target, edit=False):
    stats = db_stats()
    fragment_status = "✅ Активен" if fragment_client else "❌ Не настроен"
    text = (
        f'<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Панель администратора</b>\n\n'
        f'<tg-emoji emoji-id="5870772616305839506">👥</tg-emoji> Пользователей: {stats["users"]}\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Заказов: {stats["orders"]}\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Выполнено: {stats["completed"]}\n'
        f'<tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji> Оборот: {stats["revenue"]}₽\n\n'
        f'<tg-emoji emoji-id="5870930636742595124">⭐</tg-emoji> 1 Star = {STAR_SELL_PRICE:.2f}₽\n'
        f'<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> 1 TON = {TON_RUB:.2f}₽\n'
        f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> Курс: {LAST_UPDATE_TIME}\n'
        f'<tg-emoji emoji-id="5940433880585605708">🔨</tg-emoji> Fragment API: {fragment_status}'
    )
    if edit:
        try:
            await target.edit_text(text, reply_markup=admin_keyboard())
            return
        except:
            pass
    await target.answer(text, reply_markup=admin_keyboard())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    stats = db_stats()
    text = (
        f'<b><tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> Статистика</b>\n\n'
        f'<tg-emoji emoji-id="5870772616305839506">👥</tg-emoji> Пользователей: {stats["users"]}\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Заказов: {stats["orders"]}\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Выполнено: {stats["completed"]}\n'
        f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Ошибок: {stats["failed"]}\n'
        f'<tg-emoji emoji-id="5904462880941545555">🪙</tg-emoji> Оборот: {stats["revenue"]}₽'
    )
    try:
        await cb.message.edit_text(text, reply_markup=admin_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=admin_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    text = '<b><tg-emoji emoji-id="6039422865189638057">📣</tg-emoji> Рассылка</b>\n\nОтправьте сообщение:'
    try:
        await cb.message.edit_text(text)
    except:
        await cb.message.delete()
        await cb.message.answer(text)
    await state.set_state(BroadcastState.waiting_for_message)
    await cb.answer()

@dp.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    text = '<b><tg-emoji emoji-id="5769126056262898415">👛</tg-emoji> Добавить баланс</b>\n\nВведите Telegram ID пользователя:'
    try:
        await cb.message.edit_text(text)
    except:
        await cb.message.delete()
        await cb.message.answer(text)
    await state.set_state(AddBalanceState.waiting_for_user_id)
    await cb.answer()

@dp.message(AddBalanceState.waiting_for_user_id)
async def add_balance_user_id(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        user_id = int(msg.text.strip())
    except:
        await msg.answer("❌ Введите корректный ID!")
        return
    user = db_get_user(user_id)
    if not user:
        await msg.answer("❌ Пользователь не найден!")
        return
    await state.update_data(target_user_id=user_id)
    await msg.answer(
        f'👤 {user["full_name"]}\n'
        f'💰 Баланс: {user["balance"]}₽\n\nВведите сумму:'
    )
    await state.set_state(AddBalanceState.waiting_for_amount)

@dp.message(AddBalanceState.waiting_for_amount)
async def add_balance_amount(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        amount = float(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await msg.answer("❌ Введите корректную сумму!")
        return
    data = await state.get_data()
    user_id = data["target_user_id"]
    db_add_balance(user_id, amount)
    new_balance = db_get_balance(user_id)
    await state.clear()
    await msg.answer(f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Зачислено {amount}₽\n💰 Новый баланс: {new_balance}₽')
    try:
        await bot.send_message(
            user_id,
            f'<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Администратор пополнил баланс!\n'
            f'💰 +{amount}₽\n📊 Новый баланс: {new_balance}₽'
        )
    except:
        pass

@dp.message(BroadcastState.waiting_for_message)
async def do_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    users = db_get_all_users()
    sent, failed = 0, 0
    status_msg = await msg.answer(
        f'<tg-emoji emoji-id="5345906554510012647">🔄</tg-emoji> Рассылка {len(users)} пользователям...'
    )
    for user in users:
        try:
            await bot.copy_message(user["id"], msg.from_user.id, msg.message_id)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await state.clear()
    await status_msg.edit_text(
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Рассылка завершена: '
        f'отправлено {sent}, ошибок {failed}'
    )

# ═══════════════════════════════════════════════════════════════
#  Запуск
# ═══════════════════════════════════════════════════════════════

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    db_init()
    await update_prices()

    fragment_ok = init_fragment_client()
    if fragment_ok:
        logging.info("✅ Fragment API активен — автоматическая отправка Stars/Premium включена")
    else:
        logging.warning(
            "⚠️  Fragment API не активен. Проверьте TON_SEED в .env\n"
            "    Seeds должен быть 12 или 24 слова через пробел."
        )

    asyncio.create_task(price_updater_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

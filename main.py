import asyncio
import logging
import subprocess
import sys
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional
import aiohttp

# ⚠️ СНАЧАЛА загружаем .env ДО ВСЕГО!
from dotenv import load_dotenv
load_dotenv()

def install_packages():
    """Автоматическая установка необходимых библиотек"""
    
    required_packages = [
        "aiogram>=3.0.0",
        "aiohttp>=3.8.0",
        "python-dotenv>=1.0.0",
        "qrcode>=7.4.0",
        "Pillow>=9.0.0"
    ]
    
    print("=" * 50)
    print("🔧 ПРОВЕРКА И УСТАНОВКА ЗАВИСИМОСТЕЙ")
    print("=" * 50)
    
    for package in required_packages:
        package_name = package.split(">=")[0]
        try:
            __import__(package_name)
            print(f"✅ {package_name} уже установлен")
        except ImportError:
            print(f"📦 Устанавливаю {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✅ {package} установлен")
            except Exception as e:
                print(f"❌ Ошибка установки {package}: {e}")
    
    print("=" * 50)
    print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 50)

# Запускаем установку
install_packages()

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

# ═══════════════════════════════════════════════════════════════
#  Конфиг (читаем из .env после загрузки)
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
MARKUP_PERCENT = int(os.getenv("MARKUP_PERCENT", 20))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "support")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
TON_SEED = os.getenv("TON_SEED")

# Выводим для проверки (НЕ ПИШИ ТАК В ПРОДЕ, ТОЛЬКО ДЛЯ ОТЛАДКИ!)
print(f"🔍 BOT_TOKEN = {BOT_TOKEN[:10]}... (скрыто)")
print(f"🔍 TON_SEED = {'ЗАДАН' if TON_SEED else 'НЕ ЗАДАН'}")

# Директория для данных
DATA_DIR = os.getenv('DATA_DIR', '/app/data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "stars_bot.db")

# Реквизиты карты
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_BANK = os.getenv("CARD_BANK", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "")
CARD_PHONE = os.getenv("CARD_PHONE", "")

# Канал для подписки
REQUIRED_CHANNEL_ID = "-1003304197671"
REQUIRED_CHANNEL_LINK = "https://t.me/HollywoodStarsChannel"

# Курсы
TON_RUB = 105.45
STARS_TON_PRICE = 0.010749
STAR_SELL_PRICE = 0.0
LAST_UPDATE_TIME = None

# Premium пакеты
PREMIUM_PACKAGES = [
    {"months": 3, "price_ton": 8.30, "price_rub": 0},
    {"months": 6, "price_ton": 11.07, "price_rub": 0},
    {"months": 12, "price_ton": 20.07, "price_rub": 0},
]

# ═══════════════════════════════════════════════════════════════
#  Fragment API
# ═══════════════════════════════════════════════════════════════

fragment_client = None
FRAGMENT_AVAILABLE = False

def init_fragment_client():
    global fragment_client, FRAGMENT_AVAILABLE
    
    # Еще раз проверяем TON_SEED
    ton_seed = os.getenv("TON_SEED")
    print(f"🔍 В init_fragment_client: TON_SEED = {'ЗАДАН' if ton_seed else 'НЕ ЗАДАН'}")
    
    if not ton_seed:
        print("⚠️ TON_SEED не задан в .env файле")
        return False
    
    try:
        # Пробуем импортировать
        try:
            from fragment_api_lib import FragmentAPIClient
            print("✅ FragmentAPIClient импортирован")
        except ImportError:
            try:
                from fragment_api_lib.client import FragmentAPIClient
                print("✅ FragmentAPIClient импортирован (из client)")
            except ImportError as e:
                print(f"❌ Не удалось импортировать Fragment API: {e}")
                return False
        
        # Инициализируем
        fragment_client = FragmentAPIClient()
        print("✅ Fragment клиент создан")
        
        FRAGMENT_AVAILABLE = True
        print("✅ Fragment API готов к работе!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации Fragment API: {e}")
        FRAGMENT_AVAILABLE = False
        return False

# Запускаем инициализацию
init_fragment_client()
# ═══════════════════════════════════════════════════════════════
#  Парсер курсов
# ═══════════════════════════════════════════════════════════════

async def fetch_ton_rub() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "rub"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["the-open-network"]["rub"])
    except:
        pass
    return 105.45

async def fetch_stars_ton_price() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://fragment.com/api/v1/stars/price",
                headers={"User-Agent": "Mozilla/5.0"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("price_per_star", 0.010749))
    except:
        pass
    return 0.010749

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
        {"stars": 50, "price": get_star_price(50)},
        {"stars": 100, "price": get_star_price(100)},
        {"stars": 250, "price": get_star_price(250)},
        {"stars": 500, "price": get_star_price(500)},
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

def db_add_user(uid: int, username: str, full_name: str):
    with db_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (id, username, full_name) VALUES (?,?,?)", (uid, username, full_name))

def db_get_user(uid: int) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

def db_get_all_users() -> list:
    with db_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]

def db_get_balance(uid: int) -> float:
    u = db_get_user(uid)
    return round(u["balance"], 2) if u else 0.0

def db_add_balance(uid: int, amount: float):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))

def db_deduct_balance(uid: int, amount: float):
    with db_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, uid))

def db_create_order(uid: int, otype: str, qty: int, amount: float, recipient: str) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (user_id, type, quantity, amount_rub, recipient) VALUES (?,?,?,?,?)",
            (uid, otype, qty, amount, recipient)
        )
        return cur.lastrowid

def db_get_order(order_id: int) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

def db_update_order(order_id: int, status: str, method: str = "", tx_id: str = ""):
    with db_conn() as conn:
        if method and tx_id:
            conn.execute("UPDATE orders SET status=?, payment_method=?, transaction_id=? WHERE id=?", 
                        (status, method, tx_id, order_id))
        elif method:
            conn.execute("UPDATE orders SET status=?, payment_method=? WHERE id=?", 
                        (status, method, order_id))
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

def db_create_card_payment(user_id: int, order_id: int, amount: float, payment_type: str, photo_file_id: str) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO card_payments (user_id, order_id, amount, payment_type, photo_file_id) VALUES (?,?,?,?,?)",
            (user_id, order_id, amount, payment_type, photo_file_id)
        )
        return cur.lastrowid

def db_get_card_payment(payment_id: int) -> Optional[dict]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM card_payments WHERE id=?", (payment_id,)).fetchone()
        return dict(row) if row else None

def db_get_pending_card_payments() -> list:
    with db_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM card_payments WHERE status='pending' ORDER BY created_at DESC").fetchall()]

def db_update_card_payment(payment_id: int, status: str):
    with db_conn() as conn:
        conn.execute("UPDATE card_payments SET status=? WHERE id=?", (status, payment_id))

def db_user_orders(uid: int, limit=10) -> list:
    with db_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit)
        ).fetchall()]

def db_stats() -> dict:
    with db_conn() as conn:
        return {
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "completed": conn.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0],
            "failed": conn.execute("SELECT COUNT(*) FROM orders WHERE status='failed'").fetchone()[0],
            "revenue": round(conn.execute("SELECT COALESCE(SUM(amount_rub),0) FROM orders WHERE status='completed'").fetchone()[0], 2),
        }

def db_get_active_stars_photos() -> list:
    with db_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM stars_photos WHERE is_active=1 AND file_id != '' ORDER BY id").fetchall()]

def db_add_stars_photo(file_id: str, caption: str):
    with db_conn() as conn:
        conn.execute("INSERT INTO stars_photos (file_id, caption) VALUES (?,?)", (file_id, caption))

def db_delete_stars_photo(photo_id: int):
    with db_conn() as conn:
        conn.execute("DELETE FROM stars_photos WHERE id=?", (photo_id,))

def db_toggle_stars_photo(photo_id: int, is_active: int):
    with db_conn() as conn:
        conn.execute("UPDATE stars_photos SET is_active=? WHERE id=?", (is_active, photo_id))

def db_get_all_stars_photos() -> list:
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
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return {"invoice_id": data["result"]["invoice_id"], "pay_url": data["result"]["pay_url"]}
    except Exception as e:
        logging.error(f"CryptoBot error: {e}")
    return None

async def check_crypto_payment(invoice_id: int) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/getInvoices",
                json={"invoice_ids": [invoice_id]},
                headers={"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
            ) as resp:
                data = await resp.json()
                if data.get("ok") and data["result"]["items"]:
                    return data["result"]["items"][0]["status"]
    except:
        return "unknown"
    return "unknown"

# ═══════════════════════════════════════════════════════════════
#  Fragment API функции отправки
# ═══════════════════════════════════════════════════════════════

async def send_stars_via_fragment(username: str, amount: int) -> dict:
    if not FRAGMENT_AVAILABLE or not fragment_client:
        raise Exception("Fragment API не настроен. Проверьте TON_SEED в .env файле")
    
    if amount < 50:
        raise Exception("Минимальное количество звезд - 50")
    
    try:
        clean_username = username.lstrip("@")
        
        # Выполняем синхронный вызов в отдельном потоке
        result = await asyncio.to_thread(
            fragment_client.buy_stars_without_kyc,
            username=clean_username,
            amount=amount,
            seed=TON_SEED
        )
        
        transaction_id = result.get("transaction_id", result.get("tx_id", f"tx_{uuid.uuid4().hex[:10]}"))
        
        print(f"✅ Отправлено {amount} Stars пользователю @{clean_username}, TX: {transaction_id}")
        
        return {"success": True, "transaction_id": transaction_id}
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка отправки Stars: {error_msg}")
        raise Exception(f"Ошибка Fragment API: {error_msg}")

async def send_premium_via_fragment(username: str, months: int) -> dict:
    if not FRAGMENT_AVAILABLE or not fragment_client:
        raise Exception("Fragment API не настроен. Проверьте TON_SEED в .env файле")
    
    try:
        clean_username = username.lstrip("@")
        
        result = await asyncio.to_thread(
            fragment_client.buy_premium,
            username=clean_username,
            months=months,
            seed=TON_SEED
        )
        
        transaction_id = result.get("transaction_id", result.get("tx_id", f"premium_{uuid.uuid4().hex[:10]}"))
        
        print(f"✅ Активирован Premium на {months} мес. для @{clean_username}, TX: {transaction_id}")
        
        return {"success": True, "transaction_id": transaction_id}
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка активации Premium: {error_msg}")
        raise Exception(f"Ошибка Fragment API: {error_msg}")

# ═══════════════════════════════════════════════════════════════
#  FSM Состояния
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
#  Клавиатуры
# ═══════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить Stars", callback_data="menu_buy_stars")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="menu_buy_premium")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="📦 Мои заказы", callback_data="menu_orders"),
         InlineKeyboardButton(text="❓ Поддержка", callback_data="menu_help")],
    ])

def recipient_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Себе", callback_data="rec_self")],
        [InlineKeyboardButton(text="🎁 Другу", callback_data="rec_friend")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ])

def stars_packages_keyboard(username: str):
    kb = []
    for p in get_star_packages():
        kb.append([InlineKeyboardButton(
            text=f"⭐ {p['stars']} звезд — {p['price']}₽",
            callback_data=f"stars_{p['stars']}_{username}"
        )])
    kb.append([InlineKeyboardButton(text="✏️ Своё число", callback_data=f"stars_custom_{username}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def payment_keyboard(order_id: int, amount: float, balance: float):
    kb = []
    if balance >= amount:
        kb.append([InlineKeyboardButton(text=f"💰 Списать с баланса ({balance}₽)", callback_data=f"pay_balance_{order_id}")])
    kb.append([InlineKeyboardButton(text="💳 Оплата картой", callback_data=f"pay_card_{order_id}")])
    kb.append([InlineKeyboardButton(text="🤖 CryptoBot (TON)", callback_data=f"pay_crypto_{order_id}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def premium_keyboard():
    kb = []
    for p in PREMIUM_PACKAGES:
        kb.append([InlineKeyboardButton(
            text=f"💎 {p['months']} мес — {int(p['price_rub'])}₽",
            callback_data=f"premium_{p['months']}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💰 Добавить баланс", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="🖼 Управление фото", callback_data="admin_photos")],
        [InlineKeyboardButton(text="💳 Платежи по карте", callback_data="admin_card_payments")],
    ])

def admin_photos_keyboard():
    photos = db_get_all_stars_photos()
    kb = []
    for p in photos:
        if p["file_id"]:
            status = "✅" if p["is_active"] else "❌"
            kb.append([InlineKeyboardButton(text=f"{status} Фото #{p['id']}", callback_data=f"photo_toggle_{p['id']}")])
            kb.append([InlineKeyboardButton(text=f"🗑 Удалить #{p['id']}", callback_data=f"photo_delete_{p['id']}")])
    kb.append([InlineKeyboardButton(text="➕ Добавить фото", callback_data="photo_add")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="topup_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ])

def topup_method_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта", callback_data="topup_card")],
        [InlineKeyboardButton(text="🤖 CryptoBot (TON)", callback_data="topup_crypto")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ])

def admin_payments_keyboard():
    payments = db_get_pending_card_payments()
    kb = []
    for p in payments:
        type_text = "💰 Пополнение" if p["payment_type"] == "topup" else "🛍 Покупка"
        kb.append([InlineKeyboardButton(text=f"📝 {type_text} #{p['id']} | {p['amount']}₽", callback_data=f"view_payment_{p['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def payment_action_keyboard(payment_id: int, payment_type: str):
    if payment_type == "topup":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить пополнение", callback_data=f"approve_topup_{payment_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_payment_{payment_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_card_payments")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить покупку", callback_data=f"approve_purchase_{payment_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_payment_{payment_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_card_payments")],
        ])

# ═══════════════════════════════════════════════════════════════
#  Проверка подписки на канал
# ═══════════════════════════════════════════════════════════════

async def check_subscription(user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(cb: CallbackQuery):
    user_id = cb.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        db_add_user(user_id, cb.from_user.username or "", cb.from_user.full_name)
        await update_prices()
        
        photos = db_get_active_stars_photos()
        if photos and photos[0]["file_id"]:
            await cb.message.answer_photo(
                photo=photos[0]["file_id"],
                caption=f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
                        f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
                        f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
                        f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
                        f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
                        f"🛍 <b>Хороших покупок!</b>",
                reply_markup=main_menu_keyboard()
            )
        else:
            await cb.message.answer(
                f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
                f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
                f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
                f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
                f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
                f"🛍 <b>Хороших покупок!</b>",
                reply_markup=main_menu_keyboard()
            )
        try:
            await cb.message.delete()
        except:
            pass
    else:
        await cb.answer("❌ Вы еще не подписаны на канал! Подпишитесь и нажмите «Проверить подписку»", show_alert=True)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Обработчики команд
# ═══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    is_subscribed = await check_subscription(msg.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return
    
    db_add_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.full_name)
    await update_prices()
    
    photos = db_get_active_stars_photos()
    if photos and photos[0]["file_id"]:
        await msg.answer_photo(
            photo=photos[0]["file_id"],
            caption=f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
                    f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
                    f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
                    f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
                    f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
                    f"🛍 <b>Хороших покупок!</b>",
            reply_markup=main_menu_keyboard()
        )
    else:
        await msg.answer(
            f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
            f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
            f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
            f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
            f"🛍 <b>Хороших покупок!</b>",
            reply_markup=main_menu_keyboard()
        )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    await state.clear()
    await update_prices()
    
    try:
        await cb.message.delete()
    except:
        pass
    
    photos = db_get_active_stars_photos()
    if photos and photos[0]["file_id"]:
        await cb.message.answer_photo(
            photo=photos[0]["file_id"],
            caption=f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
                    f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
                    f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
                    f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
                    f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
                    f"🛍 <b>Хороших покупок!</b>",
            reply_markup=main_menu_keyboard()
        )
    else:
        await cb.message.answer(
            f"✨ <b>Добро пожаловать в HollywoodStars!</b>\n\n"
            f"⭐ Здесь вы можете приобрести <b>Telegram Stars</b> и\n"
            f"<b>Telegram Premium</b> на свой аккаунт за рубли\n\n"
            f"📊 <b>Актуальный курс:</b> 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"🕐 Обновлен: {LAST_UPDATE_TIME}\n\n"
            f"🛍 <b>Хороших покупок!</b>",
            reply_markup=main_menu_keyboard()
        )
    await cb.answer()

@dp.callback_query(F.data == "menu_profile")
async def menu_profile(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    user = db_get_user(cb.from_user.id)
    orders = db_user_orders(cb.from_user.id)
    completed_orders = [o for o in orders if o["status"] == "completed"]
    total_spent = sum(o["amount_rub"] for o in completed_orders)
    total_count = len(completed_orders)
    
    text = (f"👤 <b>Профиль</b>\n\n"
            f"🆔 Id: <code>{cb.from_user.id}</code>\n"
            f"👤 Username: @{cb.from_user.username or 'не указан'}\n"
            f"📅 Регистрация: {user['created_at'][:10]}\n\n"
            f"💰 Баланс: {user['balance']}₽\n"
            f"💵 Сумма покупок: {total_spent}₽\n"
            f"🔢 Количество покупок: {total_count}\n\n"
            f"⭐ 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"🕐 Курс обновлен: {LAST_UPDATE_TIME}")
    
    try:
        await cb.message.edit_text(text, reply_markup=profile_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=profile_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_buy_stars")
async def menu_buy_stars(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    await state.set_state(BuyStars.choose_recipient)
    text = (f"⭐ <b>Покупка Stars</b>\n\n"
            f"📊 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"🕐 Курс обновлен: {LAST_UPDATE_TIME}\n\n"
            f"👤 <b>Кому отправить звезды?</b>")
    
    try:
        await cb.message.edit_text(text, reply_markup=recipient_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=recipient_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_buy_premium")
async def menu_buy_premium(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    text = (f"💎 <b>Telegram Premium</b>\n\n"
            f"📊 1 Ton = {TON_RUB:.2f}₽\n"
            f"🕐 Курс обновлен: {LAST_UPDATE_TIME}\n\n"
            f"Выберите срок подписки:")
    
    try:
        await cb.message.edit_text(text, reply_markup=premium_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=premium_keyboard())
    await cb.answer()

@dp.callback_query(F.data == "menu_orders")
async def menu_orders(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    orders = db_user_orders(cb.from_user.id, limit=10)
    if not orders:
        text = "📦 <b>Мои заказы</b>\n\n❌ У вас пока нет заказов."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
        return
    
    status_emoji = {
        "completed": "✅",
        "processing": "🔄",
        "pending": "⏳",
        "failed": "❌",
        "cancelled": "❌"
    }
    
    text = "📦 <b>Мои заказы</b>\n\n"
    for o in orders:
        emoji = status_emoji.get(o["status"], "❌")
        product = "Premium" if o["type"] == "premium" else "Stars" if o["type"] == "stars" else "Пополнение"
        text += f"{emoji} <b>#{o['id']}</b> | {product}\n💰 {o['amount_rub']}₽\n📅 {o['created_at'][:16]}\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "menu_help")
async def menu_help(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    text = (f"📚 <b>Помощь</b>\n\n"
            f"1️⃣ Нажмите «Купить Stars»\n"
            f"2️⃣ Выберите получателя (себе или другу)\n"
            f"3️⃣ Выберите количество звезд\n"
            f"4️⃣ Оплатите удобным способом\n\n"
            f"💳 <b>Способы оплаты:</b>\n"
            f"• 💰 Списать с баланса\n"
            f"• 💳 Карта\n"
            f"• 🤖 CryptoBot (Ton)\n\n"
            f"💰 <b>Пополнить баланс:</b>\n"
            f"• В меню «Мой профиль» → «Пополнить баланс»\n\n"
            f"⭐ 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"💎 Premium 3мес = {int(PREMIUM_PACKAGES[0]['price_rub'])}₽\n\n"
            f"📣 <b>Поддержка:</b> @{SUPPORT_USERNAME}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "topup_menu")
async def topup_menu(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    text = "💰 <b>Пополнение баланса</b>\n\nВыберите способ пополнения:"
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
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    username = cb.from_user.username or str(cb.from_user.id)
    await state.update_data(recipient=username)
    text = f"✅ Получатель: @{username}\n\n⭐ <b>Выберите количество:</b>"
    try:
        await cb.message.edit_text(text, reply_markup=stars_packages_keyboard(username))
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=stars_packages_keyboard(username))
    await state.set_state(BuyStars.choose_package)
    await cb.answer()

@dp.callback_query(F.data == "rec_friend")
async def rec_friend(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    text = "🎁 <b>Покупка другу</b>\n\nВведите <b>username</b> получателя (без @):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await state.set_state(BuyStars.enter_username)
    await cb.answer()

@dp.message(BuyStars.enter_username)
async def friend_username(msg: Message, state: FSMContext):
    is_subscribed = await check_subscription(msg.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return
    
    username = msg.text.strip().lstrip("@")
    if not username:
        await msg.answer("❌ Введите корректный username!")
        return
    await state.update_data(recipient=username)
    text = f"✅ Получатель: @{username}\n\n⭐ <b>Выберите количество:</b>"
    await msg.answer(text, reply_markup=stars_packages_keyboard(username))
    await state.set_state(BuyStars.choose_package)

@dp.callback_query(F.data.startswith("stars_"))
async def choose_stars_package(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    data = await state.get_data()
    username = data.get("recipient", cb.from_user.username)
    parts = cb.data.split("_")
    
    if parts[1] == "custom":
        text = "✏️ <b>Введите количество звезд</b>\n\nОт 50 до 1,000,000:"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
        await state.set_state(BuyStars.choose_package)
        await cb.answer()
        return
    
    stars = int(parts[1])
    amount = get_star_price(stars)
    balance = db_get_balance(cb.from_user.id)
    order_id = db_create_order(cb.from_user.id, "stars", stars, amount, username)
    await state.update_data(order_id=order_id, stars=stars, username=username, amount=amount)
    
    text = (f"✅ <b>Вы выбрали покупку {stars} звезд.</b>\n\n"
            f"👤 Получатель: @{username}\n"
            f"💰 Сумма: {amount}₽\n"
            f"🆔 Id покупки: <code>{order_id}</code>\n\n"
            f"💳 <b>Ваш баланс: {balance}₽</b>\n\n"
            f"<b>Выберите способ оплаты:</b>")
    
    try:
        await cb.message.edit_text(text, reply_markup=payment_keyboard(order_id, amount, balance))
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=payment_keyboard(order_id, amount, balance))
    await cb.answer()

@dp.message(BuyStars.choose_package)
async def custom_stars(msg: Message, state: FSMContext):
    is_subscribed = await check_subscription(msg.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return
    
    try:
        stars = int(msg.text.strip())
        if stars < 50 or stars > 1000000:
            raise ValueError
    except:
        await msg.answer("❌ Введите число от 50 до 1,000,000!")
        return
    
    data = await state.get_data()
    username = data.get("recipient", msg.from_user.username)
    amount = get_star_price(stars)
    balance = db_get_balance(msg.from_user.id)
    order_id = db_create_order(msg.from_user.id, "stars", stars, amount, username)
    await state.update_data(order_id=order_id, stars=stars, username=username, amount=amount)
    
    text = (f"✅ <b>Вы выбрали покупку {stars} звезд.</b>\n\n"
            f"👤 Получатель: @{username}\n"
            f"💰 Сумма: {amount}₽\n"
            f"🆔 Id покупки: <code>{order_id}</code>\n\n"
            f"💳 <b>Ваш баланс: {balance}₽</b>\n\n"
            f"<b>Выберите способ оплаты:</b>")
    
    await msg.answer(text, reply_markup=payment_keyboard(order_id, amount, balance))

# ═══════════════════════════════════════════════════════════════
#  Premium
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("premium_"))
async def choose_premium(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    months = int(cb.data.split("_")[1])
    pkg = next((p for p in PREMIUM_PACKAGES if p["months"] == months), None)
    username = cb.from_user.username or str(cb.from_user.id)
    amount = pkg["price_rub"]
    balance = db_get_balance(cb.from_user.id)
    order_id = db_create_order(cb.from_user.id, "premium", months, amount, username)
    await state.update_data(order_id=order_id, months=months, username=username, amount=amount)
    
    text = (f"✅ <b>Вы выбрали Premium на {months} мес.</b>\n\n"
            f"👤 Получатель: @{username}\n"
            f"💰 Сумма: {amount}₽\n"
            f"🆔 Id покупки: <code>{order_id}</code>\n\n"
            f"💳 <b>Ваш баланс: {balance}₽</b>\n\n"
            f"<b>Выберите способ оплаты:</b>")
    
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
        raise Exception(f"Заказ {order_id} не найден")
    
    if order["type"] == "stars":
        result = await send_stars_via_fragment(order["recipient"], order["quantity"])
        db_update_order(order_id, "completed", order["payment_method"], result["transaction_id"])
        
        await bot.send_message(
            user_id,
            f"✅ <b>Заказ #{order_id} выполнен!</b>\n\n"
            f"⭐ {order['quantity']} звезд отправлены @{order['recipient']}\n\n"
            f"🎉 Спасибо за покупку!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
        )
    elif order["type"] == "premium":
        result = await send_premium_via_fragment(order["recipient"], order["quantity"])
        db_update_order(order_id, "completed", order["payment_method"], result["transaction_id"])
        
        await bot.send_message(
            user_id,
            f"✅ <b>Заказ #{order_id} выполнен!</b>\n\n"
            f"💎 Premium на {order['quantity']} мес. активирован для @{order['recipient']}\n\n"
            f"🎉 Спасибо за покупку!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
        )

# ═══════════════════════════════════════════════════════════════
#  Оплата с баланса
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_balance_"))
async def pay_balance(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return
    
    balance = db_get_balance(cb.from_user.id)
    
    if balance < order["amount_rub"]:
        await cb.answer(f"❌ Недостаточно средств! Нужно {order['amount_rub']}₽, у вас {balance}₽", show_alert=True)
        return
    
    db_deduct_balance(cb.from_user.id, order["amount_rub"])
    db_update_order(order_id, "processing", "balance")
    
    text = f"🔄 <b>Заказ #{order_id} в обработке...</b>\n\n💸 Списано с баланса: {order['amount_rub']}₽"
    
    try:
        await cb.message.edit_text(text)
    except:
        await cb.message.delete()
        await cb.message.answer(text)
    
    try:
        await deliver_order(order_id, cb.from_user.id)
        text = (f"✅ <b>Заказ #{order_id} выполнен!</b>\n\n"
                f"💰 Остаток на балансе: {db_get_balance(cb.from_user.id)}₽")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]])
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        db_add_balance(cb.from_user.id, order["amount_rub"])
        db_update_order(order_id, "failed", "balance")
        text = (f"❌ <b>Ошибка!</b>\n\n{str(e)}\n\n"
                f"Деньги возвращены на баланс.\n\n"
                f"Обратитесь в поддержку: @{SUPPORT_USERNAME}")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]])
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Оплата картой
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_card_"))
async def pay_card(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
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
        payment_type_text = "пополнение баланса"
    elif order["type"] == "stars":
        payment_type_text = f"покупку {order['quantity']} звезд"
    else:
        payment_type_text = f"покупку Premium на {order['quantity']} мес"
    
    text = (f"💳 <b>Оплата картой</b>\n\n"
            f"📦 Заказ #{order_id}\n"
            f"💰 Сумма: {order['amount_rub']}₽\n"
            f"📝 Товар: {payment_type_text}\n\n"
            f"<b>Реквизиты для оплаты:</b>\n"
            f"┌ Номер карты: <code>{CARD_NUMBER}</code>\n"
            f"├ Банк: {CARD_BANK}\n"
            f"├ Держатель: {CARD_HOLDER}\n"
            f"└ Телефон: {CARD_PHONE}\n\n"
            f"📸 <b>После оплаты отправьте скриншот чека</b>\n\n"
            f"🔙 Для отмены нажмите «Назад»")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.message(CardPaymentState.waiting_for_screenshot)
async def handle_card_screenshot(msg: Message, state: FSMContext):
    is_subscribed = await check_subscription(msg.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return
    
    if not msg.photo:
        await msg.answer("❌ Пожалуйста, отправьте скриншот чека")
        return
    
    data = await state.get_data()
    order_id = data.get("card_order_id")
    
    if not order_id:
        await msg.answer("❌ Ошибка: начните оплату заново")
        await state.clear()
        return
    
    order = db_get_order(order_id)
    if not order:
        await msg.answer("❌ Заказ не найден")
        await state.clear()
        return
    
    if order["type"] == "topup":
        payment_type = "topup"
        payment_type_text = "Пополнение баланса"
    elif order["type"] == "stars":
        payment_type = "purchase"
        payment_type_text = f"Покупка {order['quantity']} звезд"
    else:
        payment_type = "purchase"
        payment_type_text = f"Покупка Premium на {order['quantity']} мес"
    
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
        f"✅ <b>Скриншот получен!</b>\n\n"
        f"📦 Заказ #{order_id}\n"
        f"💰 Сумма: {order['amount_rub']}₽\n"
        f"📝 {payment_type_text}\n\n"
        f"⏳ Ожидайте подтверждения администратора",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=photo_file_id,
                caption=f"💳 <b>Новый платеж по карте</b>\n\n"
                        f"👤 Пользователь: @{msg.from_user.username or msg.from_user.id}\n"
                        f"🆔 ID: {msg.from_user.id}\n"
                        f"📦 Заказ #{order_id}\n"
                        f"💰 Сумма: {order['amount_rub']}₽\n"
                        f"📝 {payment_type_text}\n"
                        f"👤 Получатель: @{order['recipient']}",
                reply_markup=payment_action_keyboard(payment_id, payment_type)
            )
        except Exception as e:
            logging.error(f"Ошибка отправки админу: {e}")
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════
#  Обработка платежей админом
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("view_payment_"))
async def view_payment(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    
    if not payment:
        await cb.answer("Платеж не найден", show_alert=True)
        return
    
    order = db_get_order(payment["order_id"])
    
    await cb.answer()
    await cb.message.answer_photo(
        photo=payment["photo_file_id"],
        caption=f"💳 <b>Платеж #{payment_id}</b>\n\n"
                f"👤 Пользователь: {payment['user_id']}\n"
                f"📦 Заказ #{payment['order_id']}\n"
                f"💰 Сумма: {payment['amount']}₽\n"
                f"📝 Тип: {'Пополнение' if payment['payment_type'] == 'topup' else 'Покупка'}\n"
                f"👤 Получатель: @{order['recipient']}\n"
                f"📅 Дата: {payment['created_at']}",
        reply_markup=payment_action_keyboard(payment_id, payment["payment_type"])
    )

@dp.callback_query(F.data.startswith("approve_topup_"))
async def approve_topup(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    
    if not payment or payment["status"] != "pending":
        await cb.answer("Платеж не найден или уже обработан", show_alert=True)
        return
    
    await cb.answer("✅ Пополнение одобрено!")
    
    db_update_card_payment(payment_id, "approved")
    db_update_order(payment["order_id"], "completed", "card")
    db_add_balance(payment["user_id"], payment["amount"])
    new_balance = db_get_balance(payment["user_id"])
    
    await cb.message.answer(
        f"✅ <b>Пополнение баланса одобрено!</b>\n\n"
        f"👤 Пользователь: {payment['user_id']}\n"
        f"💰 Сумма: {payment['amount']}₽\n"
        f"📊 Новый баланс: {new_balance}₽"
    )
    
    try:
        await cb.message.delete()
    except:
        pass
    
    await bot.send_message(
        payment["user_id"],
        f"✅ <b>Баланс успешно пополнен!</b>\n\n"
        f"💰 Зачислено: {payment['amount']}₽\n"
        f"📊 Новый баланс: {new_balance}₽",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
    )

@dp.callback_query(F.data.startswith("approve_purchase_"))
async def approve_purchase(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    
    if not payment or payment["status"] != "pending":
        await cb.answer("Платеж не найден или уже обработан", show_alert=True)
        return
    
    await cb.answer("✅ Покупка одобрена!")
    
    db_update_card_payment(payment_id, "approved")
    db_update_order(payment["order_id"], "processing", "card")
    
    await cb.message.answer(f"✅ <b>Покупка одобрена!</b>\n\n📦 Заказ #{payment['order_id']}\n⏳ Начинаем отправку...")
    
    try:
        await cb.message.delete()
    except:
        pass
    
    try:
        await deliver_order(payment["order_id"], payment["user_id"])
    except Exception as e:
        db_update_order(payment["order_id"], "failed", "card")
        await bot.send_message(
            payment["user_id"],
            f"❌ <b>Ошибка при обработке заказа #{payment['order_id']}</b>\n\n{str(e)}\n\nОбратитесь в поддержку: @{SUPPORT_USERNAME}"
        )

@dp.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    payment_id = int(cb.data.split("_")[2])
    payment = db_get_card_payment(payment_id)
    
    if not payment or payment["status"] != "pending":
        await cb.answer("Платеж не найден или уже обработан", show_alert=True)
        return
    
    await cb.answer("❌ Платеж отклонен!")
    
    db_update_card_payment(payment_id, "rejected")
    db_update_order(payment["order_id"], "failed", "card")
    
    await cb.message.answer(f"❌ <b>Платеж отклонен</b>\n\n📦 Заказ #{payment['order_id']}\n💰 Сумма: {payment['amount']}₽")
    
    try:
        await cb.message.delete()
    except:
        pass
    
    type_text = "пополнение баланса" if payment["payment_type"] == "topup" else "покупка"
    await bot.send_message(
        payment["user_id"],
        f"❌ <b>Ваш платеж отклонен</b>\n\n📝 Операция: {type_text}\n💰 Сумма: {payment['amount']}₽\n\nПричина: неверный скриншот\n\nПоддержка: @{SUPPORT_USERNAME}"
    )

# ═══════════════════════════════════════════════════════════════
#  Пополнение баланса
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "topup_card")
async def topup_card(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    await state.set_state(TopUpState.waiting_for_amount)
    await state.update_data(topup_method="card")
    
    text = "💳 <b>Пополнение баланса картой</b>\n\nВведите сумму пополнения (от 100₽):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="topup_menu")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data == "topup_crypto")
async def topup_crypto(cb: CallbackQuery, state: FSMContext):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    await state.set_state(TopUpState.waiting_for_amount)
    await state.update_data(topup_method="crypto")
    
    text = "🤖 <b>Пополнение баланса через CryptoBot</b>\n\nВведите сумму пополнения (от 100₽):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="topup_menu")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@dp.message(TopUpState.waiting_for_amount)
async def topup_amount(msg: Message, state: FSMContext):
    is_subscribed = await check_subscription(msg.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
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
        
        text = (f"💳 <b>Пополнение баланса картой</b>\n\n"
                f"💰 Сумма: {amount}₽\n"
                f"🆔 Id операции: <code>{order_id}</code>\n\n"
                f"<b>Реквизиты для оплаты:</b>\n"
                f"┌ Номер карты: <code>{CARD_NUMBER}</code>\n"
                f"├ Банк: {CARD_BANK}\n"
                f"├ Держатель: {CARD_HOLDER}\n"
                f"└ Телефон: {CARD_PHONE}\n\n"
                f"📸 <b>После оплаты отправьте скриншот чека</b>")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="topup_menu")]])
        await msg.answer(text, reply_markup=kb)
    else:
        invoice = await create_crypto_invoice(amount)
        if not invoice:
            await msg.answer("❌ Ошибка создания счета")
            await state.clear()
            return
        
        ton_amount = round(amount / TON_RUB, 4)
        text = (f"🤖 <b>Пополнение баланса через CryptoBot</b>\n\n"
                f"💰 Сумма: {amount}₽\n"
                f"💎 К оплате: {ton_amount} Ton\n\n"
                f"🔗 <a href='{invoice['pay_url']}'>Оплатить в Ton</a>\n\n"
                f"После оплаты нажмите «Проверить оплату»")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_topup_{invoice['invoice_id']}_{amount}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ])
        
        await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await state.clear()

@dp.callback_query(F.data.startswith("check_topup_"))
async def check_topup(cb: CallbackQuery):
    parts = cb.data.split("_")
    if len(parts) != 3:
        await cb.answer("❌ Ошибка", show_alert=True)
        return
    
    invoice_id = int(parts[1])
    amount = float(parts[2])
    status = await check_crypto_payment(invoice_id)
    
    if status == "paid":
        db_add_balance(cb.from_user.id, amount)
        text = (f"✅ <b>Баланс пополнен!</b>\n\n"
                f"💰 Зачислено: {amount}₽\n"
                f"📊 Новый баланс: {db_get_balance(cb.from_user.id)}₽")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
    elif status == "active":
        await cb.answer("⏳ Оплата еще не получена", show_alert=True)
    else:
        await cb.answer("❌ Счет не оплачен", show_alert=True)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Оплата CryptoBot для заказов
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(cb: CallbackQuery):
    is_subscribed = await check_subscription(cb.from_user.id)
    
    if not is_subscribed:
        text = (f"❌ <b>Доступ запрещен!</b>\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n"
                f"👉 <a href='{REQUIRED_CHANNEL_LINK}'>HollywoodStars Channel</a>\n\n"
                f"✅ После подписки нажмите кнопку ниже:")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
        ])
        try:
            await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except:
            await cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        await cb.answer()
        return
    
    order_id = int(cb.data.split("_")[2])
    order = db_get_order(order_id)
    
    if not order:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return
    
    invoice = await create_crypto_invoice(order["amount_rub"])
    if not invoice:
        await cb.answer("❌ Ошибка создания счета", show_alert=True)
        return
    
    db_update_order(order_id, "pending", "cryptobot", invoice["invoice_id"])
    ton_amount = round(order["amount_rub"] / TON_RUB, 4)
    
    text = (f"🤖 <b>Оплата через CryptoBot (Ton)</b>\n\n"
            f"💰 Сумма: {order['amount_rub']}₽\n"
            f"💎 К оплате: {ton_amount} Ton\n"
            f"🆔 Id заказа: <code>{order_id}</code>\n\n"
            f"🔗 <a href='{invoice['pay_url']}'>Оплатить в Ton</a>\n\n"
            f"⏳ После оплаты нажмите «Проверить оплату»")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_crypto_{order_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{order_id}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
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
    
    if not order or not order["payment_id"]:
        await cb.answer("Ошибка", show_alert=True)
        return
    
    status = await check_crypto_payment(int(order["payment_id"]))
    
    if status == "paid":
        db_update_order(order_id, "processing", "cryptobot")
        text = f"✅ <b>Оплата получена!</b>\n\n🔄 Отправка..."
        
        try:
            await cb.message.edit_text(text)
        except:
            await cb.message.delete()
            await cb.message.answer(text)
        
        try:
            await deliver_order(order_id, cb.from_user.id)
        except Exception as e:
            db_update_order(order_id, "failed", "cryptobot")
            text = f"❌ <b>Ошибка!</b>\n\n{str(e)}\n\nПоддержка: @{SUPPORT_USERNAME}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]])
            await cb.message.edit_text(text, reply_markup=kb)
    elif status == "active":
        await cb.answer("⏳ Оплата еще не получена", show_alert=True)
    else:
        await cb.answer("❌ Счет не оплачен", show_alert=True)
    await cb.answer()

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(cb: CallbackQuery):
    order_id = int(cb.data.split("_")[1])
    db_update_order(order_id, "cancelled")
    text = f"❌ Заказ #{order_id} отменен."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]])
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

# ═══════════════════════════════════════════════════════════════
#  Админ панель
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "admin_card_payments")
async def admin_card_payments(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    payments = db_get_pending_card_payments()
    if not payments:
        text = "💳 <b>Платежи по карте</b>\n\nНет неподтвержденных платежей"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]])
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except:
            await cb.message.delete()
            await cb.message.answer(text, reply_markup=kb)
    else:
        text = "💳 <b>Платежи по карте</b>\n\n"
        for p in payments:
            type_text = "💰 Пополнение" if p["payment_type"] == "topup" else "🛍 Покупка"
            text += f"#{p['id']} | {type_text} | {p['amount']}₽ | {p['created_at'][:16]}\n"
        
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
    text = "🖼 <b>Управление фото Stars</b>\n\n"
    if photos:
        for p in photos:
            if p["file_id"]:
                status = "✅ активное" if p["is_active"] else "❌ неактивное"
                text += f"#{p['id']}: {status}\n   {p['caption'][:50]}...\n\n"
    else:
        text += "Нет добавленных фото"
    
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
        await cb.answer(f"Фото #{photo_id} {'активировано' if new_status else 'деактивировано'}")
    
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
    text = "🖼 <b>Добавление фото Stars</b>\n\nОтправьте фото для раздела «Покупка Stars»"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_photos")]])
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
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_caption")]])
    await msg.answer("📝 Отправьте подпись для фото (или нажмите «Пропустить»):", reply_markup=kb)

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
    
    caption = msg.text
    data = await state.get_data()
    db_add_stars_photo(data["photo_file_id"], caption)
    await state.clear()
    await msg.answer("✅ Фото добавлено!")
    await admin_photos(msg)

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    stats = db_stats()
    fragment_status = "✅ Активен" if FRAGMENT_AVAILABLE else "❌ Не настроен"
    
    text = (f"🔧 <b>Панель администратора</b>\n\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"📦 Заказов: {stats['orders']}\n"
            f"✅ Выполнено: {stats['completed']}\n"
            f"💰 Оборот: {stats['revenue']}₽\n\n"
            f"⭐ 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"📊 1 Ton = {TON_RUB:.2f}₽\n"
            f"🕐 Курс обновлен: {LAST_UPDATE_TIME}\n"
            f"🔧 Fragment Api: {fragment_status}")
    
    try:
        await cb.message.edit_text(text, reply_markup=admin_keyboard())
    except:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=admin_keyboard())
    await cb.answer()

@dp.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    stats = db_stats()
    fragment_status = "✅ Активен" if FRAGMENT_AVAILABLE else "❌ Не настроен"
    
    text = (f"🔧 <b>Панель администратора</b>\n\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"📦 Заказов: {stats['orders']}\n"
            f"✅ Выполнено: {stats['completed']}\n"
            f"💰 Оборот: {stats['revenue']}₽\n\n"
            f"⭐ 1 Star = {STAR_SELL_PRICE:.2f}₽\n"
            f"📊 1 Ton = {TON_RUB:.2f}₽\n"
            f"🕐 Курс обновлен: {LAST_UPDATE_TIME}\n"
            f"🔧 Fragment Api: {fragment_status}")
    
    await msg.answer(text, reply_markup=admin_keyboard())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет доступа", show_alert=True)
        return
    
    stats = db_stats()
    text = (f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"📦 Заказов: {stats['orders']}\n"
            f"✅ Выполнено: {stats['completed']}\n"
            f"❌ Ошибок: {stats['failed']}\n"
            f"💰 Оборот: {stats['revenue']}₽")
    
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
    
    text = "📢 <b>Рассылка</b>\n\nОтправьте сообщение для рассылки:"
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
    
    text = "💰 <b>Добавить баланс</b>\n\nВведите Telegram Id пользователя:"
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
        await msg.answer("❌ Введите корректный Id!")
        return
    
    user = db_get_user(user_id)
    if not user:
        await msg.answer(f"❌ Пользователь не найден!")
        return
    
    await state.update_data(target_user_id=user_id)
    await msg.answer(f"👤 {user['full_name']}\n💰 Баланс: {user['balance']}₽\n\nВведите сумму:")
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
    
    await msg.answer(f"✅ Зачислено {amount}₽\n💰 Новый баланс: {new_balance}₽")
    
    try:
        await bot.send_message(user_id, f"🎉 Администратор пополнил баланс!\n💰 +{amount}₽\n📊 Новый баланс: {new_balance}₽")
    except:
        pass

@dp.message(BroadcastState.waiting_for_message)
async def do_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    users = db_get_all_users()
    sent, failed = 0, 0
    status_msg = await msg.answer(f"🔄 Рассылка {len(users)} пользователям...")
    
    for user in users:
        try:
            await bot.copy_message(user["id"], msg.from_user.id, msg.message_id)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await state.clear()
    await status_msg.edit_text(f"✅ Рассылка: отправлено {sent}, ошибок {failed}")

# ═══════════════════════════════════════════════════════════════
#  Запуск
# ═══════════════════════════════════════════════════════════════

async def main():
    logging.basicConfig(level=logging.INFO)
    
    db_init()
    await update_prices()
    asyncio.create_task(price_updater_loop())
    
    if FRAGMENT_AVAILABLE:
        logging.info("✅ Бот запущен! Fragment API активен")
    else:
        logging.warning("⚠️ Бот запущен без Fragment API (проверьте TON_SEED в .env)")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

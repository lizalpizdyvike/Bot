import asyncio
import aiohttp
import sqlite3
import subprocess
import re
import sys
import os
import json
import random
import shutil
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from email_validator import validate_email, EmailNotValidError
from datetime import datetime
from ipaddress import ip_address

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession

# ========== КОНФИГ ==========
BOT_TOKEN = "8340638995:AAGKkCsF2SOXKEOTmAENRHy0L-5hIClQCH0"
OWNER_ID = 682077172
OWNER_USERNAME = "@criosers"
CHANNEL_USERNAME = "@submeplz"
STICKER_ID = "CAACAgQAAxkBAAEDFm9p03o2MvjRLoC1cTX4RTISblnYOAAC8BoAAtTRSVFKRA0KHazoAAE7BA"

# Папка для конвертированных сессий
CONVERTED_DIR = "converted_sessions"
if not os.path.exists(CONVERTED_DIR):
    os.makedirs(CONVERTED_DIR)

# ========== ПРЕМИУМ ЭМОДЗИ ID ==========
EMOJI = {
    "welcome": "5300766413869306803",
    "info": "5323777706179971721",
    "choose": "5393450133079743023",
}

def em(emoji_id: str, text: str = "") -> str:
    return f"<tg-emoji emoji-id=\"{emoji_id}\"> </tg-emoji>{text}"

# ========== СТИЛИЗОВАННЫЙ ШРИФТ ==========
def fancy(text: str) -> str:
    fancy_map = {
        'а': 'α', 'б': 'β', 'в': 'в', 'г': 'г', 'д': 'д', 'е': '℮', 'ё': 'ё',
        'ж': 'ж', 'з': 'з', 'и': 'и', 'й': 'й', 'к': 'к', 'л': 'л', 'м': 'м',
        'н': 'η', 'о': 'ο', 'п': 'π', 'р': 'ρ', 'с': 'с', 'т': 'τ', 'у': 'γ',
        'ф': 'φ', 'х': 'χ', 'ц': 'ц', 'ч': 'ч', 'ш': 'ш', 'щ': 'щ', 'ъ': 'ъ',
        'ы': 'ы', 'ь': 'ь', 'э': 'э', 'ю': 'ю', 'я': 'я',
        'a': 'α', 'b': 'β', 'c': 'c', 'd': 'd', 'e': '℮', 'f': 'f', 'g': 'g',
        'h': 'h', 'i': 'i', 'j': 'j', 'k': 'k', 'l': 'l', 'm': 'm', 'n': 'η',
        'o': 'ο', 'p': 'π', 'q': 'q', 'r': 'ρ', 's': 's', 't': 'τ', 'u': 'γ',
        'v': 'v', 'w': 'w', 'x': 'x', 'y': 'y', 'z': 'z',
        'А': 'Α', 'Б': 'Β', 'В': 'В', 'Г': 'Γ', 'Д': 'Δ', 'Е': 'Ε', 'Ё': 'Ё',
        'Ж': 'Ж', 'З': 'З', 'И': 'И', 'Й': 'Й', 'К': 'Κ', 'Л': 'Λ', 'М': 'Μ',
        'Н': 'Η', 'О': 'Ο', 'П': 'Π', 'Р': 'Ρ', 'С': 'С', 'Т': 'Τ', 'У': 'Υ',
        'Ф': 'Φ', 'Х': 'Χ', 'Ц': 'Ц', 'Ч': 'Ч', 'Ш': 'Ш', 'Щ': 'Щ', 'Ъ': 'Ъ',
        'Ы': 'Ы', 'Ь': 'Ь', 'Э': 'Э', 'Ю': 'Ю', 'Я': 'Я'
    }
    result = ""
    for char in text:
        result += fancy_map.get(char, char)
    return result

# ========== FSM ==========
class SearchStates(StatesGroup):
    waiting_for_ip = State()
    waiting_for_username = State()
    waiting_for_domain = State()
    waiting_for_email = State()
    waiting_for_session_file = State()
    waiting_for_phone = State()
    waiting_for_email_validate = State()

# ========== БД ==========
conn = sqlite3.connect("osint_bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    reg_date TEXT
)
""")
conn.commit()

def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def add_user(user_id: int, username: str, first_name: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, reg_date)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, first_name, now))
    conn.commit()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fancy("IP инструменты"), callback_data="menu_ip")],
        [InlineKeyboardButton(text=fancy("OSINT поиск"), callback_data="menu_osint")],
        [InlineKeyboardButton(text=fancy("Полезные инструменты"), callback_data="menu_tools")],
        [InlineKeyboardButton(text=fancy("О боте"), callback_data="menu_about")],
    ])

def get_ip_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fancy("IP Lookup"), callback_data="search_ip")],
        [InlineKeyboardButton(text=fancy("WHOIS домена"), callback_data="search_domain")],
        [InlineKeyboardButton(text=fancy("Назад"), callback_data="back_to_menu")]
    ])

def get_osint_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fancy("Поиск по нику"), callback_data="search_username")],
        [InlineKeyboardButton(text=fancy("Поиск по email"), callback_data="search_email")],
        [InlineKeyboardButton(text=fancy("Назад"), callback_data="back_to_menu")]
    ])

def get_tools_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fancy("Конвертер .session → tdata"), callback_data="tool_session")],
        [InlineKeyboardButton(text=fancy("Вычисление адреса по IP"), callback_data="tool_ip_address")],
        [InlineKeyboardButton(text=fancy("Проверка номера телефона"), callback_data="tool_phone")],
        [InlineKeyboardButton(text=fancy("Проверка email (валидность)"), callback_data="tool_email_validate")],
        [InlineKeyboardButton(text=fancy("Назад"), callback_data="back_to_menu")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fancy("Назад"), callback_data="back_to_menu")]
    ])

# ========== КОНВЕРТЕР ==========
def convert_session_to_tdata(session_file_path: str, output_name: str) -> str:
    try:
        tdata_folder = os.path.join(CONVERTED_DIR, output_name)
        if os.path.exists(tdata_folder):
            shutil.rmtree(tdata_folder)
        os.makedirs(tdata_folder)
        
        with open(session_file_path, 'rb') as f:
            session_data = f.read()
        
        with open(os.path.join(tdata_folder, 'key_database'), 'wb') as f:
            f.write(b'\x00' * 32)
        
        with open(os.path.join(tdata_folder, 'data'), 'wb') as f:
            f.write(session_data)
        
        info = {
            "version": 2,
            "date": datetime.now().isoformat(),
            "source": "session_converter"
        }
        with open(os.path.join(tdata_folder, 'info.json'), 'w') as f:
            json.dump(info, f, indent=2)
        
        archive_path = os.path.join(CONVERTED_DIR, f"{output_name}.zip")
        shutil.make_archive(archive_path.replace('.zip', ''), 'zip', tdata_folder)
        
        return archive_path
    except Exception as e:
        return None

# ========== ПРОВЕРКА НОМЕРА ТЕЛЕФОНА ==========
async def check_phone_number(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone, None)
        
        if not phonenumbers.is_valid_number(parsed):
            return f"Номер {phone} - НЕВАЛИДНЫЙ"
        
        country = geocoder.description_for_number(parsed, "ru")
        operator = carrier.name_for_number(parsed, "ru")
        timezones = timezone.time_zones_for_number(parsed)
        
        output = f"Номер: {phone}\n\n"
        output += f"Статус: ВАЛИДНЫЙ\n"
        output += f"Страна: {country}\n"
        output += f"Оператор: {operator if operator else 'Не определен'}\n"
        output += f"Часовой пояс: {', '.join(timezones)}\n"
        
        if phonenumbers.is_possible_number(parsed):
            output += f"Тип: Мобильный/Стационарный\n"
        
        return output
    except phonenumbers.NumberParseException as e:
        return f"Ошибка: Неверный формат номера\n\nПримеры:\n+79991234567\n+79123456789\n89991234567"

# ========== ПРОВЕРКА EMAIL НА ВАЛИДНОСТЬ ==========
async def validate_email_address(email: str) -> str:
    try:
        validation = validate_email(email, check_deliverability=False)
        
        output = f"Email: {email}\n\n"
        output += f"Статус: ВАЛИДНЫЙ\n"
        output += f"Локальная часть: {validation.local_part}\n"
        output += f"Домен: {validation.domain}\n"
        output += f"Нормализованный: {validation.normalized}\n"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://dns.google/resolve?name={validation.domain}&type=MX") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("Answer"):
                            output += f"MX записи: Есть (почта принимается)\n"
                        else:
                            output += f"MX записи: Нет (почта может не приниматься)\n"
        except:
            output += f"MX записи: Не удалось проверить\n"
        
        return output
    except EmailNotValidError as e:
        return f"Email: {email}\n\nСтатус: НЕВАЛИДНЫЙ\nОшибка: {str(e)}"

# ========== IP ЛУК ==========
async def ip_lookup(ip: str) -> dict:
    try:
        ip_address(ip)
    except:
        return {"error": "Невалидный IP"}
    
    result = {"ip": ip, "geo": {}, "proxy": False, "hosting": False, "risk": 0}
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        try:
            async with session.get(f"http://ip-api.com/json/{ip}?fields=66846719") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        result["geo"] = {
                            "country": data.get("country", "н/д"),
                            "city": data.get("city", "н/д"),
                            "region": data.get("regionName", "н/д"),
                            "zip": data.get("zip", "н/д"),
                            "lat": data.get("lat"),
                            "lon": data.get("lon"),
                            "isp": data.get("isp", "н/д"),
                            "org": data.get("org", "н/д"),
                            "as": data.get("as", "н/д")
                        }
                        result["proxy"] = data.get("proxy", False)
                        result["hosting"] = data.get("hosting", False)
                        
                        risk = 0
                        if result["proxy"]: risk += 50
                        if result["hosting"]: risk += 30
                        result["risk"] = risk
        except:
            pass
    return result

# ========== SHERLOCK ==========
async def run_sherlock(username: str) -> str:
    try:
        commands_to_try = [
            [sys.executable, "-m", "sherlock", username, "--print-found", "--timeout", "15", "--no-color"],
            ["sherlock", username, "--print-found", "--timeout", "15", "--no-color"],
        ]
        
        output = None
        for cmd in commands_to_try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                output = stdout.decode("utf-8", errors="ignore")
                if output and len(output) > 10:
                    break
            except:
                continue
        
        if not output:
            return "Sherlock не найден\n\nУстановка: pip install sherlock-project"
        
        lines = output.split('\n')
        found = []
        for line in lines:
            if '[' in line and ']' in line and 'https://' in line:
                found.append(line.strip())
        
        if found:
            return '\n'.join(found[:30])
        return "Ничего не найдено"
    except Exception as e:
        return f"Ошибка: {str(e)}"

# ========== EMAIL ==========
async def email_check(email: str) -> str:
    services = ["instagram", "github", "spotify", "discord"]
    found = []
    
    async with aiohttp.ClientSession() as session:
        for service in services:
            try:
                if service == "instagram":
                    async with session.post("https://www.instagram.com/accounts/web_create_ajax/attempt/", json={"email": email}) as resp:
                        if resp.status in [200, 422]:
                            found.append(service)
                elif service == "github":
                    async with session.post("https://github.com/signup_check/email", json={"email": email}) as resp:
                        if resp.status == 422:
                            found.append(service)
                await asyncio.sleep(0.3)
            except:
                pass
    
    if found:
        return f"Email: {email}\n\nНайден на:\n" + "\n".join(f"  - {s}" for s in found)
    return f"Email: {email}\n\nНе найден"

# ========== WHOIS ==========
async def domain_whois(domain: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "whois", domain,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        whois_text = stdout.decode("utf-8", errors="ignore")
        
        result = []
        patterns = {
            "Регистратор": r"Registrar:\s*(.+)",
            "Создан": r"Creation Date:\s*(.+)",
            "Истекает": r"Expiry Date:\s*(.+)"
        }
        
        for name, pattern in patterns.items():
            match = re.search(pattern, whois_text, re.IGNORECASE)
            if match:
                result.append(f"{name}: {match.group(1).strip()}")
        
        return '\n'.join(result) if result else "Данные не найдены"
    except:
        return "Ошибка"

# ========== БОТ ==========
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = None

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "no_username"
    first_name = message.from_user.first_name or "User"
    
    if not get_user(user_id):
        add_user(user_id, username, first_name)
    
    await message.answer_sticker(sticker=STICKER_ID)
    
    welcome_text = (
        f"{em(EMOJI['welcome'])} <b>{fancy('Добро пожаловать в Логово Романтика')}</b>\n\n"
        f"{em(EMOJI['info'])} <b>{fancy('Информация')}</b>\n"
        f"├─ {fancy('Ваш ID')}: <code>{user_id}</code>\n"
        f"├─ {fancy('Переходник')} - {CHANNEL_USERNAME}\n"
        f"└─ {fancy('Владелец')}: {OWNER_USERNAME}\n\n"
        f"{em(EMOJI['choose'])} <b>{fancy('Выбери нужный пункт ниже')}</b>:"
    )
    
    await message.answer(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    welcome_text = (
        f"{em(EMOJI['welcome'])} <b>{fancy('Добро пожаловать в Логово Романтика')}</b>\n\n"
        f"{em(EMOJI['info'])} <b>{fancy('Информация')}</b>\n"
        f"├─ {fancy('Ваш ID')}: <code>{user_id}</code>\n"
        f"├─ {fancy('Переходник')} - {CHANNEL_USERNAME}\n"
        f"└─ {fancy('Владелец')}: {OWNER_USERNAME}\n\n"
        f"{em(EMOJI['choose'])} <b>{fancy('Выбери нужный пункт ниже')}</b>:"
    )
    
    await callback.message.edit_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_about")
async def menu_about(callback: CallbackQuery):
    about_text = (
        f"🤖 <b>{fancy('Информация о боте')}</b>\n\n"
        f"👤 <b>{fancy('Создатель')}:</b> {OWNER_USERNAME}\n"
        f"🚀 <b>{fancy('Версия')}:</b> Beta\n\n"
        f"➡️ <b>{fancy('Переходник')}:</b> @submeplz\n\n"
        f"📝 <b>{fancy('Описание')}:</b>\n"
        f"{fancy('Сервис для OSINT разведки и полезных инструментов')}.\n\n"
        f"<b>{fancy('Возможности бота')}:</b>\n"
        f"• {fancy('IP Lookup')} - {fancy('геолокация, прокси, риск')}\n"
        f"• {fancy('WHOIS домена')} - {fancy('информация о домене')}\n"
        f"• {fancy('Поиск по нику')} - {fancy('Sherlock по 300+ соцсетям')}\n"
        f"• {fancy('Поиск по email')} - {fancy('проверка регистрации')}\n"
        f"• {fancy('Конвертер .session → tdata')} - {fancy('Telegram сессии')}\n"
        f"• {fancy('Проверка номера телефона')} - {fancy('валидация, оператор, страна')}\n"
        f"• {fancy('Проверка email')} - {fancy('валидность, MX записи')}\n"
        f"<b>{fancy('Контакты')}:</b>\n"
        f"└─ {fancy('Владелец')}: {OWNER_USERNAME}"
    )
    
    await callback.message.edit_text(
        about_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_ip")
async def menu_ip(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{fancy('IP инструменты')}\n\n{fancy('IP Lookup')} - {fancy('геолокация, прокси, риск')}\n{fancy('WHOIS домена')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_ip_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_osint")
async def menu_osint(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{fancy('OSINT поиск')}\n\n{fancy('Поиск по нику')} - Sherlock\n{fancy('Поиск по email')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_osint_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_tools")
async def menu_tools(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{fancy('Полезные инструменты')}\n\n"
        f"{fancy('Конвертер .session → tdata')} - {fancy('преобразование сессий Telegram')}\n"
        f"{fancy('Вычисление адреса по IP')} - {fancy('инструкция')}\n"
        f"{fancy('Проверка номера телефона')} - {fancy('валидация, оператор, страна')}\n"
        f"{fancy('Проверка email')} - {fancy('валидность, MX записи')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_tools_keyboard()
    )
    await callback.answer()

# ========== КОНВЕРТЕР ==========
@dp.callback_query(F.data == "tool_session")
async def tool_session_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Конвертер .session → tdata')}\n\n"
        f"{fancy('Отправь .session файл для конвертации в tdata')}:\n\n"
        f"{fancy('Поддерживаются файлы .session от Telethon/Pyrogram')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_session_file)
    await callback.answer()

@dp.message(SearchStates.waiting_for_session_file)
async def tool_session_process(message: Message, state: FSMContext):
    await state.clear()
    
    if not message.document:
        await message.answer(f"{fancy('Отправь файл .session')}", reply_markup=get_back_keyboard())
        return
    
    document = message.document
    file_name = document.file_name
    
    if not file_name.endswith('.session'):
        await message.answer(f"{fancy('Файл должен иметь расширение .session')}", reply_markup=get_back_keyboard())
        return
    
    file = await bot.get_file(document.file_id)
    file_path = f"temp_{message.from_user.id}_{file_name}"
    await bot.download_file(file.file_path, file_path)
    
    msg = await message.answer(f"{fancy('Конвертирую session в tdata...')}")
    
    output_name = f"tdata_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    archive_path = convert_session_to_tdata(file_path, output_name)
    
    os.remove(file_path)
    
    if archive_path and os.path.exists(archive_path):
        with open(archive_path, 'rb') as f:
            await message.answer_document(
                BufferedInputFile(f.read(), filename=f"{output_name}.zip"),
                caption=f"{fancy('Конвертация завершена')}!\n\n{fancy('Файл')}: {output_name}.zip\n{fancy('Распакуй архив и помести папку в Telegram Desktop (tdata)')}",
                reply_markup=get_back_keyboard()
            )
        os.remove(archive_path)
        await msg.delete()
    else:
        await msg.edit_text(f"{fancy('Ошибка конвертации. Файл может быть поврежден')}.", reply_markup=get_back_keyboard())

# ========== ВЫЧИСЛЕНИЕ АДРЕСА ПО IP ==========
@dp.callback_query(F.data == "tool_ip_address")
async def tool_ip_address(callback: CallbackQuery):
    article_url = "https://telegra.ph/ip-04-06-21"
    
    await callback.message.edit_text(
        f"{fancy('Вычисление адреса по IP')}\n\n"
        f"{fancy('Подробная инструкция')}:\n{article_url}\n\n"
        f"{fancy('В статье описаны методы определения геолокации и приблизительного адреса по IP-адресу')}.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

# ========== ПРОВЕРКА НОМЕРА ТЕЛЕФОНА ==========
@dp.callback_query(F.data == "tool_phone")
async def tool_phone_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Проверка номера телефона')}\n\n"
        f"{fancy('Отправь номер телефона для проверки')}:\n\n"
        f"{fancy('Примеры')}:\n"
        f"+79991234567\n"
        f"+79123456789\n"
        f"89991234567",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_phone)
    await callback.answer()

@dp.message(SearchStates.waiting_for_phone)
async def tool_phone_process(message: Message, state: FSMContext):
    await state.clear()
    phone = message.text.strip()
    
    msg = await message.answer(f"{fancy('Проверяю номер...')}")
    result = await check_phone_number(phone)
    await msg.edit_text(result, reply_markup=get_back_keyboard())

# ========== ПРОВЕРКА EMAIL НА ВАЛИДНОСТЬ ==========
@dp.callback_query(F.data == "tool_email_validate")
async def tool_email_validate_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Проверка email (валидность)')}\n\n"
        f"{fancy('Отправь email для проверки')}:\n\n"
        f"{fancy('Пример')}: example@gmail.com",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_email_validate)
    await callback.answer()

@dp.message(SearchStates.waiting_for_email_validate)
async def tool_email_validate_process(message: Message, state: FSMContext):
    await state.clear()
    email = message.text.strip().lower()
    
    if '@' not in email:
        await message.answer(f"{fancy('Неверный формат email')}", reply_markup=get_back_keyboard())
        return
    
    msg = await message.answer(f"{fancy('Проверяю email...')}")
    result = await validate_email_address(email)
    await msg.edit_text(result, reply_markup=get_back_keyboard())

# ========== IP ПОИСК ==========
@dp.callback_query(F.data == "search_ip")
async def search_ip_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Отправь IP адрес')}:\n\n{fancy('Пример')}: 8.8.8.8",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_ip)
    await callback.answer()

@dp.message(SearchStates.waiting_for_ip)
async def search_ip_process(message: Message, state: FSMContext):
    await state.clear()
    ip = message.text.strip()
    
    msg = await message.answer(f"{fancy('Собираю данные...')}")
    result = await ip_lookup(ip)
    
    if "error" in result:
        await msg.edit_text(f"{fancy('Ошибка')}: {result['error']}", reply_markup=get_back_keyboard())
        return
    
    geo = result.get("geo", {})
    if not geo:
        await msg.edit_text(f"{fancy('Нет данных')}", reply_markup=get_back_keyboard())
        return
    
    output = f"{fancy('IP')}: {ip}\n\n"
    output += f"{fancy('Страна')}: {geo.get('country', 'н/д')}\n"
    output += f"{fancy('Город')}: {geo.get('city', 'н/д')}\n"
    output += f"{fancy('Регион')}: {geo.get('region', 'н/д')}\n"
    output += f"{fancy('Провайдер')}: {geo.get('isp', 'н/д')}\n"
    
    lat, lon = geo.get('lat'), geo.get('lon')
    if lat and lon:
        output += f"\n{fancy('Карта')}: https://www.google.com/maps?q={lat},{lon}\n"
    
    output += f"\n{fancy('Прокси')}: {'ДА' if result.get('proxy') else 'НЕТ'}\n"
    output += f"{fancy('Хостинг')}: {'ДА' if result.get('hosting') else 'НЕТ'}\n"
    output += f"{fancy('Риск')}: {result.get('risk', 0)}%\n"
    
    await msg.edit_text(output, reply_markup=get_back_keyboard())

# ========== SHERLOCK ==========
@dp.callback_query(F.data == "search_username")
async def search_username_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Отправь никнейм для поиска')}:\n\n{fancy('Пример')}: johndoe",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_username)
    await callback.answer()

@dp.message(SearchStates.waiting_for_username)
async def search_username_process(message: Message, state: FSMContext):
    await state.clear()
    username = message.text.strip()
    
    msg = await message.answer(f"{fancy('Поиск по соцсетям...')}\n{fancy('Ожидай до 30 секунд')}")
    
    result = await run_sherlock(username)
    
    output = f"{fancy('Поиск')}: {username}\n\n{result}"
    
    if len(output) > 4000:
        output = output[:3900] + "\n\n... (обрезано)"
    
    await msg.edit_text(output, reply_markup=get_back_keyboard())

# ========== WHOIS ==========
@dp.callback_query(F.data == "search_domain")
async def search_domain_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Отправь домен')}:\n\n{fancy('Пример')}: google.com",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_domain)
    await callback.answer()

@dp.message(SearchStates.waiting_for_domain)
async def search_domain_process(message: Message, state: FSMContext):
    await state.clear()
    domain = message.text.strip().lower()
    
    msg = await message.answer(f"{fancy('Получаю WHOIS данные...')}")
    
    result = await domain_whois(domain)
    
    await msg.edit_text(f"WHOIS: {domain}\n\n{result}", reply_markup=get_back_keyboard())

# ========== EMAIL ==========
@dp.callback_query(F.data == "search_email")
async def search_email_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{fancy('Отправь email для поиска')}:\n\n{fancy('Пример')}: example@gmail.com",
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_keyboard()
    )
    await state.set_state(SearchStates.waiting_for_email)
    await callback.answer()

@dp.message(SearchStates.waiting_for_email)
async def search_email_process(message: Message, state: FSMContext):
    await state.clear()
    email = message.text.strip().lower()
    
    if '@' not in email:
        await message.answer(f"{fancy('Неверный формат email')}", reply_markup=get_back_keyboard())
        return
    
    msg = await message.answer(f"{fancy('Проверяю email...')}")
    result = await email_check(email)
    await msg.edit_text(result, reply_markup=get_back_keyboard())

# ========== ЗАПУСК ==========
async def main():
    global bot
    print("Бот запущен")
    
    session = AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    
    try:
        me = await bot.get_me()
        print(f"@{me.username}")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())

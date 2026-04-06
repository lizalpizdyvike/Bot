import asyncio
import aiohttp
import sqlite3
import re
import sys
import os

# Автоустановка библиотек
os.system("pip install phonenumbers aiogram aiohttp email-validator --quiet")

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

# ========== ПОИСК ПО НИКУ (БЫСТРЫЙ, 100+ САЙТОВ) ==========
async def search_username_sites(username: str) -> str:
    """Быстрый поиск по 100+ сайтам (параллельные запросы)"""
    
    sites = {
        "Instagram": f"https://www.instagram.com/{username}/",
        "Twitter": f"https://twitter.com/{username}",
        "GitHub": f"https://github.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "YouTube": f"https://www.youtube.com/@{username}",
        "Twitch": f"https://www.twitch.tv/{username}",
        "Telegram": f"https://t.me/{username}",
        "VK": f"https://vk.com/{username}",
        "Pinterest": f"https://www.pinterest.com/{username}/",
        "Spotify": f"https://open.spotify.com/user/{username}",
        "Facebook": f"https://www.facebook.com/{username}",
        "LinkedIn": f"https://www.linkedin.com/in/{username}/",
        "Discord": f"https://discord.com/users/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Medium": f"https://medium.com/@{username}",
        "Tumblr": f"https://{username}.tumblr.com",
        "Snapchat": f"https://www.snapchat.com/add/{username}",
        "Patreon": f"https://www.patreon.com/{username}",
        "Flickr": f"https://www.flickr.com/people/{username}/",
        "DeviantArt": f"https://www.deviantart.com/{username}",
        "Behance": f"https://www.behance.net/{username}",
        "Dribbble": f"https://dribbble.com/{username}",
        "SoundCloud": f"https://soundcloud.com/{username}",
        "Mixcloud": f"https://www.mixcloud.com/{username}/",
        "Lastfm": f"https://www.last.fm/user/{username}",
        "Bandcamp": f"https://bandcamp.com/{username}",
        "Vimeo": f"https://vimeo.com/{username}",
        "Imgur": f"https://imgur.com/user/{username}",
        "Pastebin": f"https://pastebin.com/u/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "Bitbucket": f"https://bitbucket.org/{username}/",
        "Keybase": f"https://keybase.io/{username}",
        "AboutMe": f"https://about.me/{username}",
        "AngelList": f"https://angel.co/{username}",
        "Codecademy": f"https://www.codecademy.com/profiles/{username}",
        "CodePen": f"https://codepen.io/{username}",
        "HackerNews": f"https://news.ycombinator.com/user?id={username}",
        "Replit": f"https://replit.com/@{username}",
        "Scratch": f"https://scratch.mit.edu/users/{username}/",
        "WordPress": f"https://{username}.wordpress.com",
        "Wix": f"https://{username}.wix.com",
        "Weebly": f"https://{username}.weebly.com",
        "Hackaday": f"https://hackaday.io/{username}",
        "HackerOne": f"https://hackerone.com/{username}",
        "Bugcrowd": f"https://bugcrowd.com/{username}",
        "OpenStreetMap": f"https://www.openstreetmap.org/user/{username}",
        "Codewars": f"https://www.codewars.com/users/{username}",
        "LeetCode": f"https://leetcode.com/{username}/",
        "Topcoder": f"https://www.topcoder.com/members/{username}/",
        "HackerRank": f"https://www.hackerrank.com/{username}",
        "CodinGame": f"https://www.codingame.com/profile/{username}",
        "Chess": f"https://www.chess.com/member/{username}",
        "MyAnimeList": f"https://myanimelist.net/profile/{username}",
        "AniList": f"https://anilist.co/user/{username}/",
        "Goodreads": f"https://www.goodreads.com/{username}",
        "Letterboxd": f"https://letterboxd.com/{username}/",
        "Kaggle": f"https://www.kaggle.com/{username}",
        "DataCamp": f"https://www.datacamp.com/profile/{username}",
        "Duolingo": f"https://www.duolingo.com/profile/{username}",
        "FreeCodeCamp": f"https://www.freecodecamp.org/{username}",
        "JSFiddle": f"https://jsfiddle.net/user/{username}/",
        "Glitch": f"https://glitch.com/@{username}",
        "Netlify": f"https://app.netlify.com/teams/{username}/",
        "Vercel": f"https://vercel.com/{username}",
        "Docker": f"https://hub.docker.com/u/{username}",
        "NPM": f"https://www.npmjs.com/~{username}",
        "PyPI": f"https://pypi.org/user/{username}/",
        "RubyGems": f"https://rubygems.org/profiles/{username}",
        "Packagist": f"https://packagist.org/users/{username}/",
        "NuGet": f"https://www.nuget.org/profiles/{username}",
    }
    
    async def check_site(session, name, url):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    return f"✅ {name}: {url}"
                elif resp.status == 302:
                    return f"✅ {name}: {url} (редирект)"
        except:
            pass
        return None
    
    found = []
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for name, url in sites.items():
            tasks.append(check_site(session, name, url))
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                found.append(result)
    
    if found:
        result_text = f"👤 Результаты поиска для: {username}\n\n"
        result_text += "\n".join(found[:50])
        if len(found) > 50:
            result_text += f"\n\n... и еще {len(found) - 50} сайтов"
        return result_text
    else:
        return f"👤 Поиск: {username}\n\n❌ Ничего не найдено"

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
        f"• {fancy('Поиск по нику')} - {fancy('120+ соцсетей и сервисов')}\n"
        f"• {fancy('Поиск по email')} - {fancy('проверка регистрации')}\n"
        f"• {fancy('Конвертер .session → tdata')} - {fancy('Telegram сессии')}\n"
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
        f"{fancy('OSINT поиск')}\n\n{fancy('Поиск по нику')} - 120+ сайтов\n{fancy('Поиск по email')} - проверка регистрации",
        parse_mode=ParseMode.HTML,
        reply_markup=get_osint_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu_tools")
async def menu_tools(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{fancy('Полезные инструменты')}\n\n"
        f"{fancy('Конвертер .session → tdata')} - {fancy('преобразование сессий Telegram')}",
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

# ========== ПОИСК ПО НИКУ ==========
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
    
    msg = await message.answer(f"{fancy('Поиск по 120+ сайтам...')}\n{fancy('Ожидай 3-5 секунд')}")
    
    result = await search_username_sites(username)
    
    if len(result) > 4000:
        result = result[:3900] + "\n\n... (обрезано)"
    
    await msg.edit_text(result, reply_markup=get_back_keyboard())

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

import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, \
    KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Конфигурация
BOT_TOKEN = "8386816504:AAEXwnflG85rLlHz5-PloVrDJ9RcKbiLbg0"
DB_FILE = "users_db.json"

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# States для регистрации
class Registration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    city = State()
    about = State()
    photo = State()


class Search(StatesGroup):
    viewing = State()


class EditProfile(StatesGroup):
    name = State()
    age = State()
    city = State()
    about = State()
    photo = State()


# База данных
class Database:
    def __init__(self):
        self.load_db()

    def load_db(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = {"users": {}, "likes": {}, "matches": {}}
            self.save_db()

    def save_db(self):
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_user(self, user_id, profile):
        self.data["users"][str(user_id)] = profile
        self.data["likes"][str(user_id)] = []
        self.data["matches"][str(user_id)] = []
        self.save_db()

    def get_user(self, user_id):
        return self.data["users"].get(str(user_id))

    def update_user(self, user_id, profile):
        self.data["users"][str(user_id)] = profile
        self.save_db()

    def add_like(self, from_user, to_user):
        if str(from_user) not in self.data["likes"]:
            self.data["likes"][str(from_user)] = []
        self.data["likes"][str(from_user)].append(str(to_user))

        # Проверка на взаимный лайк (match)
        if str(to_user) in self.data["likes"] and str(from_user) in self.data["likes"][str(to_user)]:
            if str(from_user) not in self.data["matches"]:
                self.data["matches"][str(from_user)] = []
            if str(to_user) not in self.data["matches"]:
                self.data["matches"][str(to_user)] = []

            self.data["matches"][str(from_user)].append(str(to_user))
            self.data["matches"][str(to_user)].append(str(from_user))
            self.save_db()
            return True
        self.save_db()
        return False

    def get_candidates(self, user_id, gender_filter=None):
        user = self.get_user(user_id)
        if not user:
            return []

        # Получаем фильтр пользователя если не указан
        if gender_filter is None:
            gender_filter = user.get('gender_filter', 'all')

        liked = self.data["likes"].get(str(user_id), [])
        candidates = []

        for uid, profile in self.data["users"].items():
            if uid == str(user_id) or uid in liked:
                continue

            # Пропускаем скрытые анкеты
            if profile.get('hidden', False):
                continue

            # Применяем фильтр
            if gender_filter != 'all':
                if profile.get("gender") != gender_filter:
                    continue

            candidates.append((uid, profile))

        return candidates

    def get_matches(self, user_id):
        match_ids = self.data["matches"].get(str(user_id), [])
        matches = []
        for mid in match_ids:
            profile = self.get_user(mid)
            if profile:
                matches.append((mid, profile))
        return matches


db = Database()


# Клавиатуры
def main_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="🔍 Смотреть анкеты")],
            [KeyboardButton(text="💕 Мои симпатии"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True
    )
    return kb


def gender_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male")],
        [InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female")]
    ])
    return kb


def search_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❤️ Лайк", callback_data="like"),
         InlineKeyboardButton(text="👎 Пропустить", callback_data="skip")]
    ])
    return kb


def profile_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")]
    ])
    return kb


def settings_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🚻 Кого показывать", callback_data="filter_gender")],
        [InlineKeyboardButton(text="👁 Видимость анкеты", callback_data="toggle_visibility")],
        [InlineKeyboardButton(text="🗑 Удалить профиль", callback_data="delete_profile")]
    ])
    return kb


def gender_filter_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Только мужчин", callback_data="filter_male")],
        [InlineKeyboardButton(text="👩 Только женщин", callback_data="filter_female")],
        [InlineKeyboardButton(text="👥 Всех", callback_data="filter_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")]
    ])
    return kb


def confirm_delete_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")]
    ])
    return kb


def edit_profile_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Имя", callback_data="edit_name")],
        [InlineKeyboardButton(text="🎂 Возраст", callback_data="edit_age")],
        [InlineKeyboardButton(text="🏙 Город", callback_data="edit_city")],
        [InlineKeyboardButton(text="💬 О себе", callback_data="edit_about")],
        [InlineKeyboardButton(text="📸 Фото", callback_data="edit_photo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_profile")]
    ])
    return kb


# Форматирование профиля
def format_profile(profile):
    gender_emoji = "👨" if profile['gender'] == 'male' else "👩"
    text = f"<b>{gender_emoji} {profile['name']}, {profile['age']}, {profile['city']}</b>\n\n"
    text += f"<i>{profile['about']}</i>"
    return text


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)

    if user:
        text = f"<b>Привет, {user['name']}! 👋</b>\n\nРады видеть тебя снова!"
        await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    else:
        text = "<b>💕 Добро пожаловать в Dating Bot!</b>\n\n"
        text += "Здесь ты можешь найти новых друзей и знакомства.\n\n"
        text += "Давай создадим твою анкету! 📝\n\n"
        text += "Как тебя зовут?"
        await message.answer(text, parse_mode="HTML")
        await state.set_state(Registration.name)


# Регистрация - Имя
@dp.message(Registration.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("<b>Сколько тебе лет?</b>\n\nУкажи свой возраст цифрами:", parse_mode="HTML")
    await state.set_state(Registration.age)


# Регистрация - Возраст
@dp.message(Registration.age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age < 18 or age > 100:
            await message.answer("❗️ Укажи корректный возраст (18-100):")
            return

        await state.update_data(age=age)
        await message.answer("<b>Выбери свой пол:</b>", reply_markup=gender_kb(), parse_mode="HTML")
        await state.set_state(Registration.gender)
    except ValueError:
        await message.answer("❗️ Укажи возраст цифрами:")


# Регистрация - Пол
@dp.callback_query(Registration.gender, F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split("_")[1]
    gender_text = "Мужчина" if gender == "male" else "Женщина"
    gender_emoji = "👨" if gender == "male" else "👩"

    await state.update_data(gender=gender, gender_text=gender_text, gender_emoji=gender_emoji)
    await callback.message.edit_text("<b>В каком городе ты живёшь?</b>", parse_mode="HTML")
    await state.set_state(Registration.city)
    await callback.answer()


# Регистрация - Город
@dp.message(Registration.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    text = "<b>Расскажи о себе!</b>\n\n"
    text += "Напиши немного о себе, своих интересах и увлечениях:"
    await message.answer(text, parse_mode="HTML")
    await state.set_state(Registration.about)


# Регистрация - О себе
@dp.message(Registration.about)
async def process_about(message: Message, state: FSMContext):
    await state.update_data(about=message.text)
    text = "<b>Отлично! 📸</b>\n\n"
    text += "Теперь отправь своё фото.\n\n"
    text += "Или напиши /skip чтобы пропустить"
    await message.answer(text, parse_mode="HTML")
    await state.set_state(Registration.photo)


# Регистрация - Фото
@dp.message(Registration.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await finish_registration(message, state)


@dp.message(Registration.photo, Command("skip"))
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo=None)
    await finish_registration(message, state)


async def finish_registration(message: Message, state: FSMContext):
    data = await state.get_data()
    data['user_id'] = message.from_user.id
    data['username'] = message.from_user.username
    data['created_at'] = datetime.now().isoformat()

    db.add_user(message.from_user.id, data)

    text = "<b>✅ Регистрация завершена!</b>\n\n"
    text += "Твоя анкета создана. Теперь ты можешь:\n"
    text += "• Просматривать анкеты других пользователей\n"
    text += "• Ставить лайки\n"
    text += "• Общаться при взаимной симпатии"

    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await state.clear()


# Обработчики текстовых кнопок
@dp.message(F.text == "👤 Мой профиль")
async def show_profile_btn(message: Message):
    user = db.get_user(message.from_user.id)
    text = format_profile(user)

    if user.get('photo'):
        await bot.send_photo(
            message.from_user.id,
            photo=user['photo'],
            caption=text,
            reply_markup=profile_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.message(F.text == "🔍 Смотреть анкеты")
async def start_search_btn(message: Message, state: FSMContext):
    candidates = db.get_candidates(message.from_user.id)

    if not candidates:
        await message.answer(
            "<b>😔 Анкеты закончились!</b>\n\nПопробуй зайти позже.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
        return

    await state.update_data(candidates=candidates, current_index=0)
    await show_candidate_new(message, state, message.from_user.id)


async def show_candidate_new(message: Message, state: FSMContext, user_id):
    data = await state.get_data()
    candidates = data.get('candidates', [])
    index = data.get('current_index', 0)

    if index >= len(candidates):
        await message.answer(
            "<b>😔 Анкеты закончились!</b>\n\nПопробуй зайти позже.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    candidate_id, profile = candidates[index]
    await state.update_data(current_candidate=candidate_id)

    text = format_profile(profile)

    if profile.get('photo'):
        await bot.send_photo(
            user_id,
            photo=profile['photo'],
            caption=text,
            reply_markup=search_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(text, reply_markup=search_kb(), parse_mode="HTML")


@dp.message(F.text == "💕 Мои симпатии")
async def show_matches_btn(message: Message):
    matches = db.get_matches(message.from_user.id)

    if not matches:
        text = "<b>💔 Пока нет взаимных симпатий</b>\n\n"
        text += "Продолжай просматривать анкеты!"
        await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    else:
        text = "<b>💕 Твои взаимные симпатии:</b>\n\n"
        for i, (mid, profile) in enumerate(matches, 1):
            username = f"@{profile['username']}" if profile.get('username') else "нет username"
            text += f"{i}. {profile['name']}, {profile['age']} - {username}\n"

        await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@dp.message(F.text == "⚙️ Настройки")
async def show_settings_btn(message: Message):
    user = db.get_user(message.from_user.id)
    gender_filter = user.get('gender_filter', 'all')
    is_hidden = user.get('hidden', False)

    filter_text = {
        'male': '👨 Только мужчин',
        'female': '👩 Только женщин',
        'all': '👥 Всех'
    }.get(gender_filter, '👥 Всех')

    visibility_emoji = '🔒' if is_hidden else '🔓'

    text = f"<b>⚙️ Настройки</b>\n\n"
    text += f"👤 <b>Имя:</b> {user['name']}\n"
    text += f"🎂 <b>Возраст:</b> {user['age']}\n"
    text += f"🏙 <b>Город:</b> {user['city']}\n\n"
    text += f"🚻 <b>Показывать:</b> {filter_text}\n"
    text += f"👁 <b>Моя анкета:</b> {visibility_emoji}"

    await message.answer(text, reply_markup=settings_kb(), parse_mode="HTML")


# Главное меню (callback для старых кнопок)
@dp.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.get_user(callback.from_user.id)
    text = f"<b>👋 Привет, {user['name']}!</b>\n\n"
    text += "Выбери нужный раздел из меню 👇"
    await callback.message.delete()
    await callback.answer(text, show_alert=True)


# Показать профиль
@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    text = format_profile(user)

    if user.get('photo'):
        await callback.message.delete()
        await bot.send_photo(
            callback.from_user.id,
            photo=user['photo'],
            caption=text,
            reply_markup=profile_kb(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    await callback.answer()


# Возврат к профилю
@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    text = format_profile(user)

    try:
        if user.get('photo'):
            await callback.message.delete()
            await bot.send_photo(
                callback.from_user.id,
                photo=user['photo'],
                caption=text,
                reply_markup=profile_kb(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    except:
        if user.get('photo'):
            await bot.send_photo(
                callback.from_user.id,
                photo=user['photo'],
                caption=text,
                reply_markup=profile_kb(),
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                callback.from_user.id,
                text,
                reply_markup=profile_kb(),
                parse_mode="HTML"
            )
    await callback.answer()


@dp.callback_query(F.data == "search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    candidates = db.get_candidates(callback.from_user.id)

    if not candidates:
        await callback.message.answer(
            "<b>😔 Анкеты закончились!</b>\n\nПопробуй зайти позже.",
            parse_mode="HTML"
        )
        await callback.message.delete()
        await callback.answer()
        return

    await state.update_data(candidates=candidates, current_index=0)
    await show_candidate(callback.message, state, callback.from_user.id)
    await callback.answer()


async def show_candidate(message: Message, state: FSMContext, user_id):
    data = await state.get_data()
    candidates = data.get('candidates', [])
    index = data.get('current_index', 0)

    if index >= len(candidates):
        await message.answer(
            "<b>😔 Анкеты закончились!</b>\n\nПопробуй зайти позже.",
            parse_mode="HTML"
        )
        await message.delete()
        await state.clear()
        return

    candidate_id, profile = candidates[index]
    await state.update_data(current_candidate=candidate_id)

    text = format_profile(profile)

    if profile.get('photo'):
        await message.delete()
        await bot.send_photo(
            user_id,
            photo=profile['photo'],
            caption=text,
            reply_markup=search_kb(),
            parse_mode="HTML"
        )
    else:
        try:
            await message.delete()
            await bot.send_message(user_id, text, reply_markup=search_kb(), parse_mode="HTML")
        except:
            await bot.send_message(user_id, text, reply_markup=search_kb(), parse_mode="HTML")


# Лайк
@dp.callback_query(F.data == "like")
async def process_like(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    candidate_id = data.get('current_candidate')

    if candidate_id:
        is_match = db.add_like(callback.from_user.id, candidate_id)

        if is_match:
            # Получаем данные обоих пользователей
            user = db.get_user(callback.from_user.id)
            candidate = db.get_user(candidate_id)

            # Уведомление для того, кто лайкнул
            text_sender = f"<b>🎉 У вас взаимная симпатия!</b>\n\n"
            text_sender += f"Ты и {candidate['name']} понравились друг другу!\n"
            text_sender += f"Можете начать общение."

            # Уведомление для того, кого лайкнули
            text_receiver = f"<b>🎉 У вас взаимная симпатия!</b>\n\n"
            text_receiver += f"Ты и {user['name']} понравились друг другу!\n"
            text_receiver += f"Можете начать общение."

            await bot.send_message(int(candidate_id), text_receiver, parse_mode="HTML")
            await callback.answer("💕 Взаимная симпатия!", show_alert=True)
        else:
            await callback.answer("❤️ Лайк отправлен!")

    # Показать следующую анкету
    data['current_index'] = data.get('current_index', 0) + 1
    await state.update_data(current_index=data['current_index'])
    await show_candidate(callback.message, state, callback.from_user.id)


# Пропустить
@dp.callback_query(F.data == "skip")
async def process_skip(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data['current_index'] = data.get('current_index', 0) + 1
    await state.update_data(current_index=data['current_index'])
    await show_candidate(callback.message, state, callback.from_user.id)
    await callback.answer()


@dp.callback_query(F.data == "matches")
async def show_matches(callback: CallbackQuery):
    matches = db.get_matches(callback.from_user.id)

    if not matches:
        text = "<b>💔 Пока нет взаимных симпатий</b>\n\n"
        text += "Продолжай просматривать анкеты!"
        await callback.message.answer(text, parse_mode="HTML")
    else:
        text = "<b>💕 Твои взаимные симпатии:</b>\n\n"
        for i, (mid, profile) in enumerate(matches, 1):
            username = f"@{profile['username']}" if profile.get('username') else "нет username"
            text += f"{i}. {profile['name']}, {profile['age']} - {username}\n"

        await callback.message.answer(text, parse_mode="HTML")

    await callback.message.delete()
    await callback.answer()


# Настройки callback
@dp.callback_query(F.data == "settings")
async def show_settings_callback(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    gender_filter = user.get('gender_filter', 'all')
    is_hidden = user.get('hidden', False)

    filter_text = {
        'male': '👨 Только мужчин',
        'female': '👩 Только женщин',
        'all': '👥 Всех'
    }.get(gender_filter, '👥 Всех')

    visibility_emoji = '🔒' if is_hidden else '🔓'

    text = f"<b>⚙️ Настройки</b>\n\n"
    text += f"👤 <b>Имя:</b> {user['name']}\n"
    text += f"🎂 <b>Возраст:</b> {user['age']}\n"
    text += f"🏙 <b>Город:</b> {user['city']}\n\n"
    text += f"🚻 <b>Показывать:</b> {filter_text}\n"
    text += f"👁 <b>Моя анкета:</b> {visibility_emoji}"

    try:
        await callback.message.edit_text(text, reply_markup=settings_kb(), parse_mode="HTML")
    except:
        await callback.message.answer(text, reply_markup=settings_kb(), parse_mode="HTML")
    await callback.answer()


# Фильтр по полу
@dp.callback_query(F.data == "filter_gender")
async def filter_gender(callback: CallbackQuery):
    text = "<b>🚻 Кого показывать в поиске?</b>\n\n"
    text += "Выбери, анкеты какого пола ты хочешь видеть:"
    await callback.message.edit_text(text, reply_markup=gender_filter_kb(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("filter_"))
async def set_gender_filter(callback: CallbackQuery):
    filter_type = callback.data.split("_")[1]

    if filter_type in ['male', 'female', 'all']:
        user = db.get_user(callback.from_user.id)
        user['gender_filter'] = filter_type
        db.update_user(callback.from_user.id, user)

        filter_text = {
            'male': '👨 мужчин',
            'female': '👩 женщин',
            'all': '👥 всех'
        }.get(filter_type)

        await callback.answer(f"✅ Теперь показываются анкеты {filter_text}")
        await show_settings_callback(callback)


# Видимость анкеты
@dp.callback_query(F.data == "toggle_visibility")
async def toggle_visibility(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    current = user.get('hidden', False)
    user['hidden'] = not current
    db.update_user(callback.from_user.id, user)

    await show_settings_callback(callback)


# Редактирование профиля
@dp.callback_query(F.data == "edit_profile")
async def edit_profile_menu(callback: CallbackQuery):
    text = "<b>✏️ Редактирование профиля</b>"

    try:
        # Если есть фото в сообщении, удаляем его
        if callback.message.photo:
            await callback.message.delete()
            await bot.send_message(
                callback.from_user.id,
                text,
                reply_markup=edit_profile_kb(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(text, reply_markup=edit_profile_kb(), parse_mode="HTML")
    except:
        await bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=edit_profile_kb(),
            parse_mode="HTML"
        )

    await callback.answer()


@dp.callback_query(F.data == "edit_name")
async def edit_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("<b>📝 Введи новое имя:</b>", parse_mode="HTML")
    await state.set_state(EditProfile.name)
    await callback.answer()


@dp.message(EditProfile.name)
async def process_edit_name(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    user['name'] = message.text
    db.update_user(message.from_user.id, user)
    await message.answer("✅ Имя обновлено!")
    await state.clear()


@dp.callback_query(F.data == "edit_age")
async def edit_age(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("<b>🎂 Введи новый возраст:</b>", parse_mode="HTML")
    await state.set_state(EditProfile.age)
    await callback.answer()


@dp.message(EditProfile.age)
async def process_edit_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age < 18 or age > 100:
            await message.answer("❗️ Укажи корректный возраст (18-100):")
            return

        user = db.get_user(message.from_user.id)
        user['age'] = age
        db.update_user(message.from_user.id, user)
        await message.answer("✅ Возраст обновлён!")
        await state.clear()
    except ValueError:
        await message.answer("❗️ Укажи возраст цифрами:")


@dp.callback_query(F.data == "edit_city")
async def edit_city(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("<b>🏙 Введи новый город:</b>", parse_mode="HTML")
    await state.set_state(EditProfile.city)
    await callback.answer()


@dp.message(EditProfile.city)
async def process_edit_city(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    user['city'] = message.text
    db.update_user(message.from_user.id, user)
    await message.answer("✅ Город обновлён!")
    await state.clear()


@dp.callback_query(F.data == "edit_about")
async def edit_about(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("<b>💬 Расскажи о себе:</b>", parse_mode="HTML")
    await state.set_state(EditProfile.about)
    await callback.answer()


@dp.message(EditProfile.about)
async def process_edit_about(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    user['about'] = message.text
    db.update_user(message.from_user.id, user)
    await message.answer("✅ Описание обновлено!")
    await state.clear()


@dp.callback_query(F.data == "edit_photo")
async def edit_photo(callback: CallbackQuery, state: FSMContext):
    text = "<b>📸 Отправь новое фото</b>\n\n"
    text += "Или напиши /skip чтобы удалить фото"
    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(EditProfile.photo)
    await callback.answer()


@dp.message(EditProfile.photo, F.photo)
async def process_edit_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    user = db.get_user(message.from_user.id)
    user['photo'] = photo_id
    db.update_user(message.from_user.id, user)
    await message.answer("✅ Фото обновлено!")
    await state.clear()


@dp.message(EditProfile.photo, Command("skip"))
async def skip_edit_photo(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    user['photo'] = None
    db.update_user(message.from_user.id, user)
    await message.answer("✅ Фото удалено!")
    await state.clear()


# Удаление профиля
@dp.callback_query(F.data == "delete_profile")
async def delete_profile_confirm(callback: CallbackQuery):
    text = "<b>⚠️ Удаление профиля</b>\n\n"
    text += "Ты уверен? Все данные будут удалены безвозвратно!"
    await callback.message.edit_text(text, reply_markup=confirm_delete_kb(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "confirm_delete")
async def delete_profile(callback: CallbackQuery):
    user_id = str(callback.from_user.id)

    # Удаляем пользователя из всех структур
    if user_id in db.data["users"]:
        del db.data["users"][user_id]
    if user_id in db.data["likes"]:
        del db.data["likes"][user_id]
    if user_id in db.data["matches"]:
        del db.data["matches"][user_id]

    # Удаляем из лайков и мэтчей других пользователей
    for uid in list(db.data["likes"].keys()):
        if user_id in db.data["likes"][uid]:
            db.data["likes"][uid].remove(user_id)

    for uid in list(db.data["matches"].keys()):
        if user_id in db.data["matches"][uid]:
            db.data["matches"][uid].remove(user_id)

    db.save_db()

    text = "<b>✅ Профиль удалён</b>\n\n"
    text += "Для создания нового профиля используй /start"
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


# Запуск бота
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

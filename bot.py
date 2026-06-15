import asyncio
import os
import threading
import random
import time
from flask import Flask
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем все функции работы с БД
from database import *

# ТВОЙ ТЕСТОВЫЙ ТОКЕН
BOT_TOKEN = "7988232708:AAFTsl6zjIwnoUDk8ZmVJZuwf-4mO_5W_8o"
ADMIN_IDS = [5271890333] # Твой личный ID прописан жестко кодом

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

# ============ ДАННЫЕ ДЛЯ ЛОКАЦИЙ И ТРАНСПОРТА ============
LOCATIONS = {
    "city": {"name": "🏙 Город", "desc": "Обычные цены и базовые квесты."},
    "village": {"name": "🏡 Деревня", "desc": "Уникальный сельский магазин. Свежий воздух!"},
    "space": {"name": "🚀 Космос", "desc": "Космические артефакты и высокие награды!"}
}

TRANSPORT = {
    "bus": {"name": "🚌 Автобус", "price": 5, "delay": 15, "desc": "Дешево, но едет 15 секунд"},
    "train": {"name": "🚂 Поезд", "price": 20, "delay": 5, "desc": "Быстрее, едет 5 секунд"},
    "rocket": {"name": "🚀 Ракета", "price": 100, "delay": 0, "desc": "Моментальный прилет!"}
}

# Магазины еды (базовые цены, умножаются на локацию при необходимости, либо остаются статичными)
FOOD_SHOP = {
    "apple": {"name": "🍎 Яблоко", "price": 2, "hunger": 15},
    "meat": {"name": "🍖 Мясо", "price": 5, "hunger": 40},
    "fish": {"name": "🐟 Рыба", "price": 8, "hunger": 60}
}

# Уникальные магазины для каждой локации с собственными предметами и ценами
LOCATION_SHOPS = {
    "city": {
        "ball": {"name": "🎾 Резиновый мячик", "price": 10, "mood": 20},
        "rope": {"name": "🧶 Канат для перетягивания", "price": 25, "mood": 45},
        "laser": {"name": "🔦 Лазерная указка", "price": 50, "mood": 70},
        "mouse": {"name": "🐭 Заводная мышка", "price": 80, "mood": 95}
    },
    "village": {
        "milk": {"name": "🥛 Миска парного молока", "price": 15, "mood": 25},
        "hay": {"name": "🌾 Ароматный стог сена", "price": 30, "mood": 50},
        "boots": {"name": "🥾 Старый дедовский сапог", "price": 65, "mood": 75},
        "tractor": {"name": "🚜 Мини-трактор на радиоуправлении", "price": 150, "mood": 100}
    },
    "space": {
        "star": {"name": "⭐ Пойманая падающая звезда", "price": 100, "mood": 40},
        "alien": {"name": "👽 Плюшевый пришелец Марси", "price": 220, "mood": 65},
        "meteor": {"name": "☄️ Светящийся осколок метеорита", "price": 450, "mood": 85},
        "blaster": {"name": "🔫 Квантовый бластер бесконечности", "price": 900, "mood": 100}
    }
}

# ============ ГЛАВНОЕ МЕНЮ (КНОПКИ ВНИЗУ) ============
def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="📱 Главное меню"), types.KeyboardButton(text="🗺 Локации")],
        [types.KeyboardButton(text="📝 Квесты"), types.KeyboardButton(text="🎰 Бокс удачи")],
        [types.KeyboardButton(text="🏪 Магазин"), types.KeyboardButton(text="🏆 Топ игроков")],
        [types.KeyboardButton(text="👤 Мой ID")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Функция для начисления опыта и левелапа
def add_xp(user_id, xp_amount):
    user = get_user(user_id)
    if not user: return ""
    
    current_xp = user.get('xp', 0) + xp_amount
    current_lvl = user.get('level', 1)
    
    lvl_msg = f"\n✨ Получено +{xp_amount} XP!"
    
    while current_xp >= 1000 and current_lvl < 100:
        current_xp -= 1000
        current_lvl += 1
        lvl_msg += f"\n🎉 **ПОЗДРАВЛЯЕМ! Уровень питомца повышен до {current_lvl}!** 🎉"
        
    update_stat(user_id, 'xp', current_xp)
    update_stat(user_id, 'level', current_lvl)
    return lvl_msg

def get_pet_face(pet_type, mood, hunger):
    if mood < 30: return f"(✖╭╮✖) {pet_type} грустит..."
    if hunger < 30: return f"(º﹃º ) {pet_type} хочет кушать..."
    
    faces = {
        "🐰 Кролик": "(・x・) *прыг-прыг*",
        "🐱 Котик": "(=^･ω･^=) *мур*",
        "🐶 Собачка": "(▼・ᴥ・▼) *гав*",
        "🐹 Хомяк": "(>ω<) *хрум*",
        "🦖 Динозавр": "🦖 *ррр*"
    }
    return faces.get(pet_type, "(◕‿◕) *радуется*")

# Сюжетные квесты с рандомом в плюс/минус и малым шансом на дополнительный XP
def get_interactive_quest(task_id, location_key="city"):
    scenarios = [
        {"q": "нашел подозрительный сундук. Открываем?", "r": 20, "fail_r": -10, "txt1": "Там были алмазы! +20💎", "txt2": "Сундук укусил питомца! Потеряно -10💎"},
        {"q": "увидел торговца редкими артефактами. Довериться?", "r": 35, "fail_r": -20, "txt1": "Торговец подарил вам ценный бонус! +35💎", "txt2": "Это был воришка! Из кармана пропало -20💎"},
        {"q": "решил зайти в темную пещеру. Идем?", "r": 50, "fail_r": -15, "txt1": "Вы нашли древний клад! +50💎", "txt2": "Питомец испугался летучих мышей и выронил -15💎"}
    ]
    scene = scenarios[task_id % len(scenarios)]
    
    # Модификатор наград от локации
    markup = 3.0 if location_key == "space" else (1.5 if location_key == "village" else 1.0)
    
    return {
        "text": f"Событие №{task_id}: Твой питомец {scene['q']}",
        "btn1": "👍 Да", "btn2": "👎 Нет",
        "reward1": int(scene["r"] * markup), 
        "reward2": int(scene["fail_r"] * markup),
        "success1": scene["txt1"], "success2": scene["txt2"]
    }

class CreatePet(StatesGroup):
    waiting_for_username = State()
    waiting_for_gender = State()
    waiting_for_egg = State()
    waiting_for_pet_name = State()

class TravelState(StatesGroup):
    waiting_for_transport = State()

PROMO_CODES = {}

# ============ ХЕНДЛЕРЫ КНОПОК ПАНЕЛИ ============

@dp.message(F.text == "📱 Главное меню")
async def btn_menu(message: types.Message):
    await render_main_menu(message, message.from_user.id)

@dp.message(F.text == "👤 Мой ID")
async def btn_id(message: types.Message):
    await message.answer(f"👤 Твой Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(Command("id"))
async def cmd_my_id(message: types.Message):
    await btn_id(message)

# ============ АДМИН-КОМАНДЫ (ПРОМОКОДЫ И УРОВЕНЬ) ============

@dp.message(Command("create_promo"))
async def cmd_create_promo(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) < 5:
        await message.answer("⚠️ Использование: `/create_promo [код] [алмазы] [xp] [макс_активаций]`", parse_mode="Markdown")
        return
    
    code = args[1].lower()
    try:
        diamonds = int(args[2])
        xp = int(args[3])
        max_uses = int(args[4])
        
        PROMO_CODES[code] = {"diamonds": diamonds, "xp": xp, "max_uses": max_uses, "used_by": []}
        await message.answer(f"✅ Промокод `{code}` успешно создан!\n💎 Алмазы: {diamonds}\n✨ XP: {xp}\n👥 Лимит: {max_uses}", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Параметры должны быть числами!")

@dp.message(Command("promo"))
async def cmd_use_promo(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Введи команду так: `/promo [название_кода]`", parse_mode="Markdown")
        return
    
    code = args[1].lower()
    user_id = message.from_user.id
    if code not in PROMO_CODES:
        await message.answer("❌ Такого промокода не существует или его лимит исчерпан.")
        return
    promo = PROMO_CODES[code]
    if user_id in promo["used_by"]:
        await message.answer("❌ Ты уже активировал этот промокод!")
        return
    if len(promo["used_by"]) >= promo["max_uses"]:
        await message.answer("❌ Лимит активаций промокода закончился.")
        return
        
    promo["used_by"].append(user_id)
    add_diamonds(user_id, promo["diamonds"])
    lvl_msg = add_xp(user_id, promo["xp"])
    await message.answer(f"🎉 Промокод активирован!\nПолучено: +{promo['diamonds']}💎{lvl_msg}", parse_mode="Markdown")

@dp.message(Command("set_lvl"))
async def cmd_set_lvl(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Использование: `/set_lvl [ID_игрока] [Уровень]`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        lvl = max(1, min(100, int(args[2])))
        update_stat(target_id, 'level', lvl)
        update_stat(target_id, 'xp', 0)
        await message.answer(f"👑 Игроку `{target_id}` установлен {lvl} уровень!", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Ошибка ввода числовых параметров.")

@dp.message(Command("cheat_money"))
async def admin_cheat_money(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    add_diamonds(message.from_user.id, 5000)
    await message.answer("🤫 Зачислено +5000 читерских алмазов!")

@dp.message(Command("give"))
async def admin_give_diamonds(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    args = message.text.split()
    if len(args) < 3: return
    try:
        target_id, amount = int(args[1]), int(args[2])
        add_diamonds(target_id, amount)
        await message.answer(f"👑 Начислено {amount}💎 игроку {target_id}.")
    except: pass

# ============ СИСТЕМА ДАРЕНИЯ АЛМАЗОВ МЕЖДУ ИГРОКАМИ ============

@dp.message(Command("gift"))
async def cmd_gift_diamonds(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "⚠️ **Как правильно дарить алмазы:**\n"
            "Введи команду вот так:\n"
            "`/gift [ID_получателя] [количество]`\n\n"
            "Пример: `/gift 5271890333 10`", 
            parse_mode="Markdown"
        )
        return
    try:
        target_id = int(args[1])
        amount = int(args[2])
        sender_id = message.from_user.id
        
        if sender_id == target_id:
            await message.answer("❌ Нельзя дарить алмазы самому себе!")
            return
            
        success, msg = transfer_diamonds(sender_id, target_id, amount)
        await message.answer(msg, parse_mode="Markdown")
        
        if success:
            try:
                await bot.send_message(
                    target_id, 
                    f"🎉 Тебе подарок!\nИгрок `{sender_id}` отправил тебе **{amount}** 💎!", 
                    parse_mode="Markdown"
                )
            except Exception: pass
    except ValueError:
        await message.answer("❌ Ошибка! ID игрока и количество алмазов должны быть числами.")

# ============ СИСТЕМА ЛОКАЦИЙ И ПУТЕШЕСТВИЙ ============

@dp.message(F.text == "🗺 Локации")
async def show_locations(message: types.Message):
    user = get_user(message.from_user.id)
    current_loc = user.get('location', 'city') if user else 'city'
    loc_name = LOCATIONS.get(current_loc, {}).get('name', '🏙 Город')
    
    text = f"📍 Твоя текущая локация: **{loc_name}**\n\nВыбери локацию для путешествия:"
    buttons = []
    for k, v in LOCATIONS.items():
        if k != current_loc:
            buttons.append([types.InlineKeyboardButton(text=f"Переехать в {v['name']}", callback_data=f"travel_to_{k}")])
            
    await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("travel_to_"))
async def choose_transport(callback: types.CallbackQuery, state: FSMContext):
    target_loc = callback.data.replace("travel_to_", "")
    await state.update_data(target_loc=target_loc)
    
    text = f"Выбери транспорт для поездки в {LOCATIONS[target_loc]['name']}:"
    buttons = []
    for k, v in TRANSPORT.items():
        buttons.append([types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}💎) | Ожидание: {v['delay']}с", callback_data=f"buy_trip_{k}")])
        
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("buy_trip_"))
async def start_trip(callback: types.CallbackQuery, state: FSMContext):
    tr_key = callback.data.replace("buy_trip_", "")
    data = await state.get_data()
    target_loc = data.get("target_loc")
    user_id = callback.from_user.id
    
    if not target_loc: return
    tr = TRANSPORT[tr_key]
    
    if not remove_diamonds(user_id, tr['price']):
        await callback.answer("❌ Недостаточно алмазов для билета!", show_alert=True)
        return
        
    await callback.message.edit_text(f"⏳ Поездка началась на {tr['name']}! Ждем прибытия {tr['delay']} сек...")
    if tr['delay'] > 0:
        await asyncio.sleep(tr['delay'])
        
    update_stat(user_id, 'location', target_loc)
    await callback.message.answer(f"🎉 Прибыли! Добро пожаловать в **{LOCATIONS[target_loc]['name']}**!", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await state.clear()

# ============ СТАРТ И СОЗДАНИЕ ПИТОМЦА ============

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user and user.get('pet_name'):
        await message.answer(f"Твой питомец уже ждет тебя в главном меню!", reply_markup=get_main_keyboard())
        return
    create_user(message.from_user.id, message.from_user.first_name)
    await message.answer("Привет! Давай создадим тебе питомца. Как мне к тебе обращаться?", reply_markup=get_main_keyboard())
    await state.set_state(CreatePet.waiting_for_username)

@dp.message(CreatePet.waiting_for_username, F.text)
async def get_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=" Мальчик", callback_data="gender_male"),
         types.InlineKeyboardButton(text=" Девочка", callback_data="gender_female")]
    ])
    await message.answer("Выбери пол для будущего питомца:", reply_markup=keyboard)
    await state.set_state(CreatePet.waiting_for_gender)

@dp.callback_query(CreatePet.waiting_for_gender, F.data.startswith("gender_"))
async def get_gender(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(pet_gender=callback.data.replace("gender_", ""))
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🌸 Магическое Яйцо", callback_data="egg_magic")],
        [types.InlineKeyboardButton(text="🔮 Неоновое Яйцо", callback_data="egg_neon")]
    ])
    await callback.message.answer("Перед тобой два таинственных яйца. Какое выберешь?", reply_markup=keyboard)
    await state.set_state(CreatePet.waiting_for_egg)
    await callback.answer()

@dp.callback_query(CreatePet.waiting_for_egg, F.data.startswith("egg_"))
async def get_egg(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(egg_type=callback.data.replace("egg_", ""))
    pet_types = ["🐰 Кролик", "🐱 Котик", "🐶 Собачка", "🐹 Хомяк", "🦖 Динозавр"]
    chosen_type = random.choice(pet_types)
    await state.update_data(pet_type=chosen_type)
    await callback.message.answer(f"Скорлупа треснула! На свет появился замечательный {chosen_type}.\n\nНапиши, какое имя ты ему дашь?")
    await state.set_state(CreatePet.waiting_for_pet_name)
    await callback.answer()

@dp.message(CreatePet.waiting_for_pet_name, F.text)
async def save_pet_name(message: types.Message, state: FSMContext):
    pet_name = message.text.strip()
    data = await state.get_data()
    update_user_pet_info(message.from_user.id, pet_name, data['pet_gender'], data['pet_type'], data['egg_type'])
    add_diamonds(message.from_user.id, 15)
    await message.answer("🎉 Питомец успешно создан! Панель управления находится кнопками внизу экрана.", reply_markup=get_main_keyboard())
    await state.clear()

# ============ РЕНДЕР ГЛАВНОГО МЕНЮ ============
async def render_main_menu(message: types.Message, user_id: int, edit: bool = False):
    user = get_user(user_id)
    if not user or not user.get('pet_name'):
        await message.answer("У тебя еще нет питомца. Напиши /start!")
        return

    update_all_stats(user_id)
    stats = get_stats(user_id)
    ascii_pic = get_pet_face(user['pet_type'], stats['mood'], stats['hunger'])
    
    current_loc = user.get('location', 'city')
    loc_name = LOCATIONS.get(current_loc, {}).get('name', '🏙 Город')
    lvl = user.get('level', 1)
    xp = user.get('xp', 0)
    
    text = (
        f" Имя: {user['pet_name']} ({user['pet_type']})\n"
        f" Уровень: **{lvl}** ({xp}/1000 XP) ✨\n"
        f" Локация: **{loc_name}** 📍\n"
        f" Баланс: {user['diamonds']}💎\n\n"
        f"    {ascii_pic}\n\n"
        f"🍖 Голод: {stats['hunger']}%/100%\n"
        f"😊 Настроение: {stats['mood']}%/100%\n"
        f"⚡ Энергия: {stats['energy']}%/100%\n"
        f"❤️ Здоровье: {stats['health']}%/100%"
    )
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🍖 Покормить", callback_data="act_feed_menu"),
         types.InlineKeyboardButton(text="🎾 Поиграть", callback_data="act_game_menu")],
        [types.InlineKeyboardButton(text="🛌 Уложить спать (2💎)", callback_data="act_sleep")]
    ])
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ============ КОРМЛЕНИЕ И ИГРЫ (+XP ЗА ДЕЙСТВИЯ) ============

@dp.callback_query(F.data == "act_feed_menu")
async def feed_menu(callback: types.CallbackQuery):
    buttons = []
    for k, v in FOOD_SHOP.items():
        buttons.append([types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}💎, +{v['hunger']}% сытости)", callback_data=f"feed_{k}")])
    buttons.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    await callback.message.edit_text("Выбери еду из общих запасов:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("feed_"))
async def process_feed(callback: types.CallbackQuery):
    food_key = callback.data.replace("feed_", "")
    food = FOOD_SHOP[food_key]
    
    if remove_diamonds(callback.from_user.id, food['price']):
        update_stat(callback.from_user.id, 'hunger', food['hunger'])
        lvl_msg = add_xp(callback.from_user.id, 60) # +60 XP за кормление
        await callback.message.edit_text(f"🍽 Питомец сыт! Голод уменьшен.{lvl_msg}", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]]))
    else:
        await callback.answer("У тебя не хватает алмазов на еду!", show_alert=True)

@dp.callback_query(F.data == "act_game_menu")
async def game_menu(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    loc = user.get('location', 'city') if user else 'city'
    current_shop = LOCATION_SHOPS.get(loc, LOCATION_SHOPS["city"])
    
    buttons = []
    for k, v in current_shop.items():
        buttons.append([types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}💎, +{v['mood']}% настроения)", callback_data=f"play_{k}")])
    buttons.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    await callback.message.edit_text("Выбери игрушку из текущего магазина локации:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("play_"))
async def process_game(callback: types.CallbackQuery):
    toy_key = callback.data.replace("play_", "")
    user = get_user(callback.from_user.id)
    loc = user.get('location', 'city') if user else 'city'
    
    current_shop = LOCATION_SHOPS.get(loc, LOCATION_SHOPS["city"])
    toy = current_shop.get(toy_key)
    
    if not toy: return
    if remove_diamonds(callback.from_user.id, toy['price']):
        update_stat(callback.from_user.id, 'mood', toy['mood'])
        lvl_msg = add_xp(callback.from_user.id, 80) # +80 XP за игру
        await callback.message.edit_text(f"🎲 Вы отлично поиграли в {toy['name']}!{lvl_msg}", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]]))
    else:
        await callback.answer("Не хватает алмазов для этой игрушки!", show_alert=True)

@dp.callback_query(F.data == "act_sleep")
async def process_sleep(callback: types.CallbackQuery):
    if remove_diamonds(callback.from_user.id, 2):
        update_stat(callback.from_user.id, 'energy', 35)
        lvl_msg = add_xp(callback.from_user.id, 100) # +100 XP за сон
        await callback.message.edit_text(f"🛌 Питомец уснул и восстановил силы.{lvl_msg}", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]]))
    else:
        await callback.answer("Недостаточно алмазов!", show_alert=True)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    await render_main_menu(callback.message, callback.from_user.id, edit=True)
    await callback.answer()

# ============ ЛУТБОКС (РАНДОМ НА ПЛЮС И МИНУС) ============
@dp.message(F.text == "🎰 Бокс удачи")
async def open_lucky_box(message: types.Message):
    user_id = message.from_user.id
    if not remove_diamonds(user_id, 5):
        await message.answer("Открытие бокса стоит 5 алмазов.")
        return
        
    msg = await message.answer("🎰 Коробка открывается...\n[❓] [❓] [❓]")
    await asyncio.sleep(1)
    
    loot_type = random.choice(["win_diamonds", "lose_diamonds", "xp", "nothing"])
    if loot_type == "win_diamonds":
        win = random.randint(10, 30)
        add_diamonds(user_id, win)
        await msg.edit_text(f"🎁 Фортуна! Из коробки высыпались сокровища: +{win}💎")
    elif loot_type == "lose_diamonds":
        loss = random.randint(5, 12)
        remove_diamonds(user_id, loss)
        await msg.edit_text(f"💥 Бабах! Коробка оказалась ловушкой! Потеряно -{loss}💎")
    elif loot_type == "xp":
        lvl_msg = add_xp(user_id, 250)
        await msg.edit_text(f"✨ Внутри была капсула времени!{lvl_msg}")
    else:
        await msg.edit_text("💨 Из коробки вылетел лишь легкий дымок. Пусто.")

# ============ ИНТЕРАКТИВНЫЕ КВЕСТЫ (С ШАНСОМ НА ДОП XP) ============
@dp.message(F.text == "📝 Квесты")
async def show_interactive_quest_msg(message: types.Message):
    user = get_user(message.from_user.id)
    if not user: return
    
    task_id = user['current_task']
    loc = user.get('location', 'city')
    quest = get_interactive_quest(task_id, location_key=loc)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=quest["btn1"], callback_data=f"qst_1_{task_id}"),
         types.InlineKeyboardButton(text=quest["btn2"], callback_data=f"qst_2_{task_id}")]
    ])
    await message.answer(quest["text"], reply_markup=keyboard)

@dp.callback_query(F.data.startswith("qst_"))
async def handle_quest_choice(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    choice = parts[1]
    task_id = int(parts[2])
    user_id = callback.from_user.id
    
    user = get_user(user_id)
    if not user or user['current_task'] != task_id: return
        
    loc = user.get('location', 'city')
    quest = get_interactive_quest(task_id, location_key=loc)
    next_task(user_id)
    
    # 1. Базовый опыт за прохождение квеста
    xp_bonus = 150
    xp_text = ""
    
    # 2. ДОБАВЛЕНО: Малый шанс (20%) на то, что выпадет дополнительный мешок опыта (+300 XP)
    if random.random() < 0.20:
        xp_bonus += 300
        xp_text = "\n🍀 **НЕВЕРОЯТНАЯ УДАЧА! Во время квеста найден скрытый свиток опыта (+300 XP сверху!)**"
        
    lvl_msg = add_xp(user_id, xp_bonus)
    
    if choice == "1":
        add_diamonds(user_id, quest["reward1"])
        await callback.message.edit_text(f"🎉 {quest['success1']}{xp_text}{lvl_msg}", parse_mode="Markdown")
    else:
        remove_diamonds(user_id, abs(quest["reward2"]))
        await callback.message.edit_text(f"❌ {quest['success2']}{xp_text}{lvl_msg}", parse_mode="Markdown")

# ============ ТАБЛИЦА ЛИДЕРОВ И УНИКАЛЬНЫЙ МАГАЗИН ============
@dp.message(F.text == "🏆 Топ игроков")
async def show_leaderboard(message: types.Message):
    top_list = get_top_users(10)
    if not top_list: return
    text = "🏆 ТАБЛИЦА ЛИДЕРОВ ИГРЫ 🏆\n\n"
    for idx, user in enumerate(top_list, 1):
        text += f"{idx}. {user['username']} — {user['diamonds']}💎 (Ур. {user.get('level', 1)})\n"
    await message.answer(text)

@dp.message(F.text == "🏪 Магазин")
async def open_shop(message: types.Message):
    user = get_user(message.from_user.id)
    loc = user.get('location', 'city') if user else 'city'
    current_shop = LOCATION_SHOPS.get(loc, LOCATION_SHOPS["city"])
    
    buttons = []
    for k, v in current_shop.items():
        buttons.append([types.InlineKeyboardButton(text=f"{v['name']} — {v['price']}💎", callback_data=f"buy_toy_{k}")])
        
    await message.answer(f"🏪 Магазин уникальных товаров в: {LOCATIONS[loc]['name']}:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("buy_toy_"))
async def buy_toy_callback(callback: types.CallbackQuery):
    toy_key = callback.data.replace("buy_toy_", "")
    user = get_user(callback.from_user.id)
    loc = user.get('location', 'city') if user else 'city'
    
    current_shop = LOCATION_SHOPS.get(loc, LOCATION_SHOPS["city"])
    toy = current_shop.get(toy_key)
    
    if not toy: 
        await callback.answer("❌ Товар исчез с прилавка!", show_alert=True)
        return
    
    if remove_diamonds(callback.from_user.id, toy['price']):
        add_item_to_inventory(callback.from_user.id, toy['name'])
        await callback.answer(f"✅ Успешно куплено: {toy['name']}", show_alert=True)
    else:
        await callback.answer("❌ Недостаточно алмазов для покупки!", show_alert=True)

# ============ ВЕБ-СЕРВЕР И СТАРТЕР ============
@app.route('/')
def health(): return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

async def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

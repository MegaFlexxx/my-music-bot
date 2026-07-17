import sys
import os
import asyncio
import requests
import json
import random
import aiohttp
import feedparser
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonWebApp, WebAppInfo, FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from aiohttp import web
from datetime import datetime, timedelta

# --- ПАТЧ ---
def apply_patch():
    try:
        import yandex_music
        if hasattr(yandex_music, 'Product'):
            original_init = yandex_music.Product.__init__
            def patched_init(self, *args, **kwargs):
                kwargs.setdefault('common_period_duration', None)
                original_init(self, *args, **kwargs)
            yandex_music.Product.__init__ = patched_init
    except ImportError: pass
apply_patch()

# --- КОНФИГ ---
TELEGRAM_TOKEN = "8632244991:AAETPh8Qsyae-d-Zos5d_QBdua6wEdFR3IU" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

# --- КАНАЛ ---
REQUIRED_CHANNEL_ID = -1001745381023
CHANNEL_LINK = "https://t.me/shkibidi_gang"

# --- БЕЛЫЙ СПИСОК ---
WHITELIST = [
    1711230756,  # ТЫ
    1425787444,  # ДРУГ
]

# --- СТАТИСТИКА ---
STATS_FILE = "user_stats.json"
ADMIN_IDS = [1711230756]

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def update_user_stats(user_id, username=None, first_name=None):
    stats = load_stats()
    user_id_str = str(user_id)
    now = datetime.now().isoformat()
    
    if user_id_str not in stats:
        stats[user_id_str] = {
            "first_seen": now,
            "last_seen": now,
            "username": username,
            "first_name": first_name,
            "total_requests": 0
        }
    else:
        stats[user_id_str]["last_seen"] = now
        if username:
            stats[user_id_str]["username"] = username
        if first_name:
            stats[user_id_str]["first_name"] = first_name
    
    stats[user_id_str]["total_requests"] += 1
    save_stats(stats)

def get_total_users():
    stats = load_stats()
    return len(stats)

def get_today_users():
    stats = load_stats()
    today = datetime.now().date()
    count = 0
    for user_id, data in stats.items():
        try:
            last_seen = datetime.fromisoformat(data["last_seen"]).date()
            if last_seen == today:
                count += 1
        except:
            pass
    return count

def get_new_users_today():
    stats = load_stats()
    today = datetime.now().date()
    count = 0
    for user_id, data in stats.items():
        try:
            first_seen = datetime.fromisoformat(data["first_seen"]).date()
            if first_seen == today:
                count += 1
        except:
            pass
    return count

# --- МОДУЛЬ ПОГОДЫ ---
WEATHER_API_KEY = "abb48920329a46d512884f6c84c71a51"

CITY_IDS = {
    "оренбург": 515853,
    "orenburg": 515853,
    "москва": 524901,
    "moscow": 524901,
    "санкт-петербург": 498817,
    "saint petersburg": 498817,
    "новосибирск": 1496747,
    "екатеринбург": 1486209,
    "казань": 551487,
    "нижний новгород": 520555,
    "челябинск": 1508291,
    "омск": 1496153,
    "самара": 499099,
    "ростов-на-дону": 501175,
    "уфа": 479561,
    "красноярск": 1502026,
    "пермь": 511196,
    "воронеж": 472045,
    "волгоград": 472757,
    "краснодар": 542420,
    "сочи": 491422,
    "лондон": 2643743,
    "london": 2643743,
    "париж": 2988507,
    "paris": 2988507,
    "берлин": 2950159,
    "berlin": 2950159,
    "нью-йорк": 5128581,
    "new york": 5128581,
}

async def get_weather_by_city(city: str):
    city_lower = city.lower().strip()
    if city_lower in CITY_IDS:
        city_id = CITY_IDS[city_lower]
        url = f"http://api.openweathermap.org/data/2.5/weather?id={city_id}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    else:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                url2 = f"http://api.openweathermap.org/data/2.5/weather?q={city},RU&appid={WEATHER_API_KEY}&units=metric&lang=ru"
                async with session.get(url2) as response2:
                    if response2.status != 200:
                        return None
                    data = await response2.json()
            else:
                data = await response.json()
            
            weather_desc = data["weather"][0]["description"].capitalize()
            temp = round(data["main"]["temp"])
            feels_like = round(data["main"]["feels_like"])
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]
            return {
                "city": data["name"],
                "description": weather_desc,
                "temp": temp,
                "feels_like": feels_like,
                "humidity": humidity,
                "wind": wind_speed,
                "icon": data["weather"][0]["icon"]
            }

# --- МОДУЛЬ ВАЛЮТ ---
async def get_currency_rates(base: str = "USD"):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{base}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                rates = {
                    "USD": data["rates"].get("USD", 0),
                    "EUR": data["rates"].get("EUR", 0),
                    "RUB": data["rates"].get("RUB", 0),
                    "CNY": data["rates"].get("CNY", 0),
                    "GBP": data["rates"].get("GBP", 0),
                    "KZT": data["rates"].get("KZT", 0),
                    "UAH": data["rates"].get("UAH", 0),
                }
                return {"base": base, "date": data.get("date", ""), "rates": rates}
    except Exception as e:
        print(f"❌ Ошибка курса валют: {e}")
        return None

# --- МОДУЛЬ КРИПТОВАЛЮТ (BINANCE) ---
async def get_crypto_prices():
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                prices = {item["symbol"]: float(item["price"]) for item in data}
                
                usd_to_rub = 88.5
                usd_to_eur = 0.92
                result = {}
                
                if "BTCUSDT" in prices:
                    btc_usd = prices["BTCUSDT"]
                    result["bitcoin"] = {"usd": btc_usd, "eur": btc_usd * usd_to_eur, "rub": btc_usd * usd_to_rub}
                if "ETHUSDT" in prices:
                    eth_usd = prices["ETHUSDT"]
                    result["ethereum"] = {"usd": eth_usd, "eur": eth_usd * usd_to_eur, "rub": eth_usd * usd_to_rub}
                if "SOLUSDT" in prices:
                    sol_usd = prices["SOLUSDT"]
                    result["solana"] = {"usd": sol_usd, "eur": sol_usd * usd_to_eur, "rub": sol_usd * usd_to_rub}
                if "TONUSDT" in prices:
                    ton_usd = prices["TONUSDT"]
                    result["toncoin"] = {"usd": ton_usd, "eur": ton_usd * usd_to_eur, "rub": ton_usd * usd_to_rub}
                
                return result if result else None
    except Exception as e:
        print(f"❌ Ошибка Binance: {e}")
        return None

# --- ПРОМО-МОДУЛЬ ---
PROMO_ENABLED = True
PROMO_IMAGES = []
if os.path.exists("promo/images"):
    for file in os.listdir("promo/images"):
        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            PROMO_IMAGES.append(f"promo/images/{file}")

PROMO_TRACKS = []
if os.path.exists("promo/tracks"):
    for file in os.listdir("promo/tracks"):
        if file.lower().endswith('.mp3'):
            PROMO_TRACKS.append({"title": os.path.splitext(file)[0], "artist": "Skibidi Sound", "url": f"promo/tracks/{file}"})

if not PROMO_IMAGES:
    PROMO_IMAGES = ["https://img.icons8.com/color/512/telegram-app.png", "https://img.icons8.com/fluency/512/music.png"]

async def send_promo_no_caption(message: types.Message):
    if not PROMO_ENABLED:
        return
    promo_type = random.choice(["image", "track"])
    if promo_type == "image" and PROMO_IMAGES:
        img_path = random.choice(PROMO_IMAGES)
        try:
            if img_path.startswith("http"):
                await message.answer_photo(photo=img_path)
            else:
                await message.answer_photo(photo=FSInputFile(img_path))
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
    elif promo_type == "track" and PROMO_TRACKS:
        track = random.choice(PROMO_TRACKS)
        try:
            await message.answer_audio(audio=FSInputFile(track["url"]), title=track["title"], performer=track["artist"])
        except Exception as e:
            print(f"Ошибка отправки трека: {e}")

# --- ИНИЦИАЛИЗАЦИЯ ---
session = AiohttpSession()
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

user_search_results = {}
user_current_position = {}

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        return member.status in ['member', 'creator', 'administrator']
    except Exception as e:
        print(f"❌ Ошибка проверки подписки: {e}")
        return False

async def check_access(user_id: int) -> bool:
    if user_id in WHITELIST:
        return True
    return await check_subscription(user_id)

# --- ПОКАЗ ТРЕКА ---
async def show_track(message: types.Message, user_id: int, position: int):
    results = user_search_results.get(user_id, [])
    if not results or position >= len(results):
        await message.answer("❌ Треки закончились!")
        return
    track = results[position]
    total = len(results)
    artists = ", ".join([a.name for a in track.artists])
    buttons = [[types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")]]
    nav_buttons = []
    if position > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{user_id}_{position-1}"))
    if position < total - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"nav_{user_id}_{position+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([types.InlineKeyboardButton(text=f"📌 {position+1}/{total}", callback_data="ignore")])
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"🎵 **{track.title}**\n👤 **Исполнитель:** {artists}\n📌 **Результат {position+1} из {total}**\n\n👇 Нажми на кнопку, чтобы скачать",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- СКАЧИВАНИЕ ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥 Ищу трек...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        info = track.get_download_info()
        link = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: 
            f.write(requests.get(link, timeout=15).content)
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_cover_url = cover_url if cover_url.startswith('http') else "https:" + cover_url
            with open(c_name, 'wb') as f: 
                f.write(requests.get(full_cover_url, timeout=10).content)
            Image.open(c_name).convert('RGB').resize((400, 400)).save(c_name, "JPEG", quality=85)
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: 
                audio.add_tags(ID3=ID3)
            with open(c_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
            audio.save(v2_version=3)
        artists = ", ".join([a.name for a in track.artists])
        track_title = track.title
        duration_sec = track.duration_ms // 1000
        minutes, seconds = duration_sec // 60, duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}"
        file_size = os.path.getsize(f_name) / (1024 * 1024)
        size_str = f"{file_size:.1f} MB"
        caption = (
            f"🔥 {track_title}\n🎤 Исполнитель: {artists}\n⏱ Длительность: {duration_str}\n💿 Размер: {size_str}\n\n🎧 Skibidi_sound бахает для тебя!"
        )
        await message.answer_audio(
            audio=types.FSInputFile(f_name),
            thumbnail=types.FSInputFile(c_name) if os.path.exists(c_name) else None,
            title=track_title,
            performer=artists,
            caption=caption
        )
        for f in [f_name, c_name]:
            if os.path.exists(f): 
                os.remove(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- ВЕБ-СЕРВЕР ---
async def handle(request): 
    return web.Response(text="Бот активен")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер на порту {port}")

# --- МЕНЮ ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="stats", description="📊 Статистика (админ)"),
        BotCommand(command="moose", description="🦌 Случайный трек/фото"),
        BotCommand(command="weather", description="🌦 Погода в городе"),
        BotCommand(command="currency", description="💰 Курс валют"),
        BotCommand(command="btc", description="🪙 Курс криптовалют"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("✅ Меню команд установлено!")

# --- КОМАНДЫ ---

@dp.message(CommandStart())
async def start_command(m: types.Message):
    update_user_stats(m.from_user.id, username=m.from_user.username, first_name=m.from_user.first_name)
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    await m.answer(
        "🎵 Skibidi_sound — твой музыкальный помощник!\n\n"
        "🔥 Отправь название трека или исполнителя, и я найду музыку!\n"
        "🎮 Или нажми кнопку 🎵 Плеер внизу экрана!\n"
        "🦌 Или введи /moose для случайного контента!\n"
        "🌦 Или введи /weather Оренбург для погоды!\n"
        "💰 Или введи /currency для курса валют!\n"
        "🪙 Или введи /btc для курса криптовалют!"
    )

@dp.message(Command("stats"))
async def stats_command(m: types.Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("❌ У тебя нет доступа к этой команде!")
        return
    total = get_total_users()
    today = get_today_users()
    new_today = get_new_users_today()
    stats = load_stats()
    sorted_users = sorted(stats.items(), key=lambda x: x[1]["last_seen"], reverse=True)[:5]
    text = f"📊 **Статистика бота**\n\n👥 **Всего пользователей:** {total}\n🆕 **Новых сегодня:** {new_today}\n📆 **Активных сегодня:** {today}\n\n📋 **Последние 5 пользователей:**\n"
    for user_id, data in sorted_users:
        name = data.get("first_name") or data.get("username") or "Аноним"
        last_seen = datetime.fromisoformat(data["last_seen"]).strftime("%d.%m %H:%M")
        text += f"• {name} — {last_seen}\n"
    await m.answer(text, parse_mode="Markdown")

@dp.message(Command("moose"))
async def moose_command(m: types.Message):
    update_user_stats(m.from_user.id, username=m.from_user.username, first_name=m.from_user.first_name)
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    await send_promo_no_caption(m)

@dp.message(Command("weather"))
async def weather_command(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.answer("🌦 Укажи город!\nНапример: /weather Оренбург или /weather Orenburg")
        return
    city_input = args[1].strip()
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    await m.answer(f"🌦 Ищу погоду в {city_input}...")
    weather = await get_weather_by_city(city_input)
    if not weather:
        await m.answer(f"❌ Город {city_input} не найден.\n💡 Попробуй написать на английском: /weather Orenburg")
        return
    emoji_map = {"01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️", "03d": "☁️", "03n": "☁️", "04d": "☁️", "04n": "☁️", "09d": "🌧", "09n": "🌧", "10d": "🌦", "10n": "🌧", "11d": "⛈", "11n": "⛈", "13d": "❄️", "13n": "❄️", "50d": "🌫", "50n": "🌫"}
    emoji = emoji_map.get(weather["icon"], "🌡️")
    text = f"{emoji} Погода в {weather['city']}\n\n🌡️ Температура: {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n💧 Влажность: {weather['humidity']}%\n💨 Ветер: {weather['wind']} м/с\n☁️ {weather['description']}"
    await m.answer(text)

@dp.message(Command("currency"))
async def currency_command(m: types.Message):
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    args = m.text.split(maxsplit=1)
    base = args[1].strip().upper() if len(args) > 1 else "USD"
    allowed = ["USD", "EUR", "RUB", "CNY", "GBP", "KZT", "UAH"]
    if base not in allowed:
        await m.answer(f"❌ Валюта {base} не поддерживается.\n💡 Доступные валюты: {', '.join(allowed)}\nПример: /currency USD")
        return
    await m.answer(f"💰 Загружаю курсы валют...")
    data = await get_currency_rates(base)
    if not data:
        await m.answer(f"❌ Не удалось загрузить курсы валют.\n💡 Попробуй позже.")
        return
    rates = data["rates"]
    emoji_map = {"USD": "🇺🇸", "EUR": "🇪🇺", "RUB": "🇷🇺", "CNY": "🇨🇳", "GBP": "🇬🇧", "KZT": "🇰🇿", "UAH": "🇺🇦"}
    text = f"💰 Курсы валют (база: {data['base']})\n📅 {data['date']}\n\n"
    main_currencies = ["RUB", "EUR", "USD", "CNY", "GBP", "KZT", "UAH"]
    for curr in main_currencies:
        if curr in rates:
            emoji = emoji_map.get(curr, "")
            text += f"{emoji} {curr} — {rates[curr]:.2f}\n"
    await m.answer(text)

@dp.message(Command("btc"))
async def btc_command(m: types.Message):
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    await m.answer("🪙 Загружаю курсы криптовалют...")
    data = await get_crypto_prices()
    if not data:
        await m.answer(f"❌ Не удалось загрузить курсы криптовалют.\n💡 Попробуй позже.")
        return
    emoji_map = {"bitcoin": "🟠", "ethereum": "🔷", "solana": "🟣", "toncoin": "🔵"}
    name_map = {"bitcoin": "Bitcoin (BTC)", "ethereum": "Ethereum (ETH)", "solana": "Solana (SOL)", "toncoin": "Toncoin (TON)"}
    text = f"🪙 Курсы криптовалют\n\n"
    for key, coin in data.items():
        if coin:
            emoji = emoji_map.get(key, "🪙")
            name = name_map.get(key, key.capitalize())
            usd = coin.get("usd", 0)
            eur = coin.get("eur", 0)
            rub = coin.get("rub", 0)
            text += f"{emoji} {name}\n   🇺🇸 ${usd:,.2f}\n   🇪🇺 €{eur:,.2f}\n   🇷🇺 {rub:,.0f} ₽\n\n"
    await m.answer(text)

# --- ПОИСК ---
@dp.message(F.text)
async def search_command(m: types.Message):
    if m.text.startswith('/'):
        return
    update_user_stats(m.from_user.id, username=m.from_user.username, first_name=m.from_user.first_name)
    if not await check_access(m.from_user.id):
        await m.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    print(f"🔍 Ищу: {m.text}")
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
        return
    res = yandex_client.search(m.text, type_='track')
    if res.tracks:
        user_id = m.from_user.id
        user_search_results[user_id] = res.tracks.results
        user_current_position[user_id] = 0
        await show_track(m, user_id, 0)
    else:
        await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

# --- WEB APP DATA ---
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    update_user_stats(message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
    if not await check_access(message.from_user.id):
        await message.answer(
            "🔒 Для доступа к боту нужно подписаться на наш канал!\n\n👇 Нажми на кнопку ниже, чтобы подписаться:\nПосле подписки нажми /start снова.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get('action')
        print(f"📩 Из плеера: {action} {data}")
        if action == 'search':
            query = data.get('query')
            if not query:
                return
            res = yandex_client.search(query, type_='track')
            if res.tracks:
                track = res.tracks.results[0]
                artists = ", ".join([a.name for a in track.artists])
                await message.answer(
                    f"✅ Нашёл для тебя!\n\n🎵 {track.title} — {artists}\n👇 Нажми кнопку, чтобы скачать",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")]])
                )
            else:
                await message.answer("❌ Ничего не найдено. Попробуй изменить запрос.")
        elif action == 'download':
            track = data.get('track')
            artist = data.get('artist')
            await message.answer(f"📥 Скачиваю: {track} — {artist}")
        elif action == 'like':
            track = data.get('track')
            await message.answer(f"❤️ Лайк: {track}")
        elif action == 'add_to_playlist':
            track = data.get('track')
            await message.answer(f"➕ Добавлено в плейлист: {track}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# --- CALLBACK ---
@dp.callback_query(F.data.startswith("down_"))
async def download_callback(c: types.CallbackQuery):
    if not await check_access(c.from_user.id):
        await c.answer("❌ Доступ запрещён!", show_alert=True)
        return
    await c.answer("🔄 Скачиваю...")
    track_id = c.data.replace("down_", "")
    await download_and_send(c.message, track_id)

@dp.callback_query(F.data.startswith("nav_"))
async def nav_callback(c: types.CallbackQuery):
    parts = c.data.split("_")
    user_id = int(parts[1])
    position = int(parts[2])
    if c.from_user.id != user_id:
        await c.answer("❌ Это не твой поиск!", show_alert=True)
        return
    user_current_position[c.from_user.id] = position
    await show_track(c.message, user_id, position)
    await c.message.delete()
    await c.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_callback(c: types.CallbackQuery):
    await c.answer()

# --- ГЛАВНАЯ ---
async def main():
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🎵 Плеер",
            web_app=WebAppInfo(url="https://megaflexxx.github.io/my-music-bot/")
        )
    )
    await set_commands()
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())

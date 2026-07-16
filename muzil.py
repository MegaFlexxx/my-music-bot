import sys
import os
import json
import asyncio
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.client.session.aiohttp import AiohttpSession
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from aiohttp import web
from datetime import datetime

# --- ПАТЧ YANDEX MUSIC ---
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

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAETPh8Qsyae-d-Zos5d_QBdua6wEdFR3IU" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

# --- JSONBIN НАСТРОЙКИ ---
JSONBIN_API_KEY = "$2a$10$CX38xBtBqOre7M6olAPo4ehOVtTcINNnDU5hpOVbvk6/VMx22C2ti"
JSONBIN_BIN_ID = "6a58c64cf5f4af5e299736cd"

session = AiohttpSession()
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ХРАНИЛИЩЕ РЕЗУЛЬТАТОВ ПОИСКА ДЛЯ КАЖДОГО ПОЛЬЗОВАТЕЛЯ ---
user_search_results = {}  # {user_id: [список треков]}
user_current_position = {}  # {user_id: текущая_позиция}

# --- СТАТИСТИКА ЧЕРЕЗ JSONBIN ---
def load_stats():
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "X-Bin-Private": "false"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            record = data.get("record", {})
            if isinstance(record, dict) and "users" in record:
                return record.get("users", {})
            return record
        else:
            print(f"❌ Ошибка загрузки: {response.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Ошибка загрузки статистики: {e}")
        return {}

def save_stats(stats):
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "Content-Type": "application/json",
            "X-Bin-Private": "false"
        }
        data_to_save = {"users": stats}
        response = requests.put(url, json=data_to_save, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Статистика сохранена в JSONBin")
        else:
            print(f"❌ Ошибка сохранения: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка сохранения статистики: {e}")

def update_stats(user_id, track_title, artist_name):
    stats = load_stats()
    user_id_str = str(user_id)
    
    if user_id_str not in stats:
        stats[user_id_str] = {
            "total_downloads": 0,
            "total_searches": 0,
            "tracks": [],
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat()
        }
    
    stats[user_id_str]["total_downloads"] += 1
    stats[user_id_str]["last_seen"] = datetime.now().isoformat()
    
    track_info = {
        "title": track_title,
        "artist": artist_name,
        "date": datetime.now().isoformat()
    }
    stats[user_id_str]["tracks"].append(track_info)
    if len(stats[user_id_str]["tracks"]) > 10:
        stats[user_id_str]["tracks"] = stats[user_id_str]["tracks"][-10:]
    
    save_stats(stats)

def update_search(user_id):
    stats = load_stats()
    user_id_str = str(user_id)
    
    if user_id_str not in stats:
        stats[user_id_str] = {
            "total_downloads": 0,
            "total_searches": 0,
            "tracks": [],
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat()
        }
    
    stats[user_id_str]["total_searches"] += 1
    stats[user_id_str]["last_seen"] = datetime.now().isoformat()
    save_stats(stats)

def get_top_users():
    stats = load_stats()
    if not stats:
        return []
    
    sorted_users = sorted(
        stats.items(),
        key=lambda x: x[1]["total_downloads"],
        reverse=True
    )[:5]
    
    return sorted_users

# --- ФУНКЦИЯ ДЛЯ ПОКАЗА ТРЕКА С КНОПКАМИ ---
async def show_track(message: types.Message, user_id: int, position: int):
    """Показывает трек на определённой позиции с кнопками"""
    results = user_search_results.get(user_id, [])
    
    if not results or position >= len(results):
        await message.answer("❌ Треки закончились!")
        return
    
    track = results[position]
    total = len(results)
    
    # Формируем кнопки
    buttons = []
    
    # Кнопка скачать
    buttons.append([types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")])
    
    # Кнопки навигации
    nav_buttons = []
    if position > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{user_id}_{position-1}"))
    if position < total - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"nav_{user_id}_{position+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Информация о прогрессе
    info_button = [types.InlineKeyboardButton(text=f"📌 {position+1}/{total}", callback_data="ignore")]
    buttons.append(info_button)
    
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Показываем трек
    artists = ", ".join([a.name for a in track.artists])
    await message.answer(
        f"🎵 **{track.title}**\n"
        f"👤 **Исполнитель:** {artists}\n"
        f"📌 **Результат {position+1} из {total}**\n\n"
        f"👇 Нажми на кнопку, чтобы скачать",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- ЛОГИКА СКАЧИВАНИЯ ---
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
        
        update_stats(message.from_user.id, track_title, artists)
        
        duration_sec = track.duration_ms // 1000
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
        file_size = os.path.getsize(f_name) / (1024 * 1024)
        size_str = f"{file_size:.1f} MB"
        
        caption = (
            f"🔥 {track_title}\n"
            f"🎤 Исполнитель: {artists}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"💿 Размер: {size_str}\n\n"
            f"🎧 Skibidi_sound бахает для тебя!"
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
    print(f"✅ Веб-сервер запущен на порту {port}")

# --- МЕНЮ КОМАНД ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="stats", description="📊 Моя статистика"),
        BotCommand(command="top", description="🏆 Топ пользователей"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("✅ Меню команд установлено!")

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer(
        "🎵 **Skibidi_sound** — твой музыкальный помощник!\n\n"
        "📌 **Команды:**\n"
        "/stats — твоя статистика\n"
        "/top — топ пользователей\n"
        "/start — показать это сообщение\n\n"
        "🔥 Отправь название трека или исполнителя, и я найду музыку за считанные секунды!",
        parse_mode="Markdown"
    )

@dp.message(Command("stats"))
async def show_stats(m: types.Message):
    user_id_str = str(m.from_user.id)
    stats = load_stats()
    
    if user_id_str not in stats:
        await m.answer("📊 У тебя пока нет скачанных треков. Начни искать музыку! 🎵")
        return
    
    user_stats = stats[user_id_str]
    total_downloads = user_stats["total_downloads"]
    total_searches = user_stats["total_searches"]
    first_seen = datetime.fromisoformat(user_stats["first_seen"]).strftime("%d.%m.%Y")
    last_seen = datetime.fromisoformat(user_stats["last_seen"]).strftime("%d.%m.%Y")
    track_count = len(user_stats["tracks"])
    
    total_sec = track_count * 180
    total_min = total_sec // 60
    total_hours = total_min // 60
    total_min_remain = total_min % 60
    
    text = (
        f"📊 **Твоя статистика**\n\n"
        f"🎵 **Скачано треков:** {total_downloads}\n"
        f"🔍 **Поисков:** {total_searches}\n"
        f"📁 **В истории:** {track_count} треков\n"
        f"⏱ **Прослушано:** {total_hours}ч {total_min_remain}мин\n"
        f"📅 **Первый раз:** {first_seen}\n"
        f"🔄 **Последний раз:** {last_seen}\n"
    )
    
    if user_stats["tracks"]:
        text += "\n📋 **Последние треки:**\n"
        for i, track in enumerate(user_stats["tracks"][-5:], 1):
            text += f"{i}. {track['artist']} — {track['title']}\n"
    
    await m.answer(text, parse_mode="Markdown")

@dp.message(Command("top"))
async def show_top(m: types.Message):
    top_users = get_top_users()
    
    if not top_users:
        await m.answer("📊 Пока нет статистики. Будь первым! 🚀")
        return
    
    text = "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ**\n\n"
    for i, (user_id, data) in enumerate(top_users, 1):
        try:
            user = await bot.get_chat(int(user_id))
            name = user.first_name or user.username or "Аноним"
        except:
            name = "Аноним"
        
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        medal = medals[i-1] if i <= 5 else f"{i}."
        
        text += f"{medal} **{name}**\n"
        text += f"   📥 Скачано: {data['total_downloads']} треков\n"
        text += f"   🔍 Поисков: {data['total_searches']}\n\n"
    
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text)
async def handle_search(m: types.Message):
    if m.text.startswith('/'):
        return
    
    update_search(m.from_user.id)
    
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
    else:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            # Сохраняем все результаты поиска для пользователя
            user_id = m.from_user.id
            user_search_results[user_id] = res.tracks.results
            user_current_position[user_id] = 0
            
            # Показываем первый трек
            await show_track(m, user_id, 0)
        else:
            await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer("🔽 Начинаю загрузку...")
    await download_and_send(c.message, c.data.split("_")[1])

@dp.callback_query(F.data.startswith("nav_"))
async def callback_navigation(c: types.CallbackQuery):
    """Обрабатывает навигацию по трекам"""
    # Разбираем данные: nav_userId_position
    parts = c.data.split("_")
    user_id = int(parts[1])
    position = int(parts[2])
    
    # Проверяем, что это тот же пользователь
    if c.from_user.id != user_id:
        await c.answer("❌ Это не твой поиск!", show_alert=True)
        return
    
    # Обновляем текущую позицию
    user_current_position[c.from_user.id] = position
    
    # Показываем трек на новой позиции
    await show_track(c.message, user_id, position)
    
    # Удаляем старые кнопки
    await c.message.delete()
    
    await c.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_callback(c: types.CallbackQuery):
    await c.answer()

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    await set_commands()
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())

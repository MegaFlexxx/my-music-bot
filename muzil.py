import sys
import os
import json
import asyncio
import re
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.client.session.aiohttp import AiohttpSession
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from aiohttp import web
from datetime import datetime

# --- SPOTIFY ---
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False
    print("⚠️ Spotify не установлен. Установи: pip install spotipy")

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
TELEGRAM_TOKEN = "8632244991:AAE58ZHOF3_TbNNlXhmHjTaSRBim1gBByQo" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

# --- SPOTIFY НАСТРОЙКИ ---
SPOTIFY_CLIENT_ID = os.environ.get("dd8639a7232b4776b68b4fdbc7d0690b")
SPOTIFY_CLIENT_SECRET = os.environ.get("1b805ef3f54640669769ebe52cb76da3")

# --- JSONBIN ---
JSONBIN_API_KEY = "$2a$10$CX38xBtBqOre7M6olAPo4ehOVtTcINNnDU5hpOVbvk6/VMx22C2ti"
JSONBIN_BIN_ID = "6a58c64cf5f4af5e299736cd"

session = AiohttpSession()
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- SPOTIFY КЛИЕНТ ---
sp = None
if SPOTIFY_AVAILABLE and SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
        print("✅ Spotify подключён!")
    except Exception as e:
        print(f"❌ Ошибка Spotify: {e}")
else:
    print("⚠️ Spotify не настроен. Используем только Яндекс.Музыку.")

# --- ХРАНИЛИЩЕ ---
user_search_results = {}
user_current_position = {}

# --- СТАТИСТИКА ---
def load_stats():
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY, "X-Bin-Private": "false"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            record = data.get("record", {})
            if isinstance(record, dict) and "users" in record:
                return record.get("users", {})
            return record
        return {}
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return {}

def save_stats(stats):
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json", "X-Bin-Private": "false"}
        response = requests.put(url, json={"users": stats}, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Статистика сохранена")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def update_stats(user_id, track_title, artist_name):
    stats = load_stats()
    user_id_str = str(user_id)
    if user_id_str not in stats:
        stats[user_id_str] = {"total_downloads": 0, "total_searches": 0, "tracks": [], "first_seen": datetime.now().isoformat(), "last_seen": datetime.now().isoformat()}
    stats[user_id_str]["total_downloads"] += 1
    stats[user_id_str]["last_seen"] = datetime.now().isoformat()
    stats[user_id_str]["tracks"].append({"title": track_title, "artist": artist_name, "date": datetime.now().isoformat()})
    if len(stats[user_id_str]["tracks"]) > 10:
        stats[user_id_str]["tracks"] = stats[user_id_str]["tracks"][-10:]
    save_stats(stats)

def update_search(user_id):
    stats = load_stats()
    user_id_str = str(user_id)
    if user_id_str not in stats:
        stats[user_id_str] = {"total_downloads": 0, "total_searches": 0, "tracks": [], "first_seen": datetime.now().isoformat(), "last_seen": datetime.now().isoformat()}
    stats[user_id_str]["total_searches"] += 1
    stats[user_id_str]["last_seen"] = datetime.now().isoformat()
    save_stats(stats)

def get_top_users():
    stats = load_stats()
    if not stats: return []
    return sorted(stats.items(), key=lambda x: x[1]["total_downloads"], reverse=True)[:5]

# --- ПОИСК В SPOTIFY ---
def search_spotify(query, limit=5):
    if not sp:
        return []
    try:
        results = sp.search(q=query, type='track', limit=limit)
        tracks = []
        for item in results['tracks']['items']:
            tracks.append({
                'id': item['id'],
                'title': item['name'],
                'artists': ", ".join([a['name'] for a in item['artists']]),
                'album': item['album']['name'],
                'cover': item['album']['images'][0]['url'] if item['album']['images'] else None,
                'duration_ms': item['duration_ms'],
                'source': 'spotify',
                'url': item['external_urls']['spotify']
            })
        return tracks
    except Exception as e:
        print(f"Spotify ошибка: {e}")
        return []

# --- ОБЪЕДИНЕНИЕ РЕЗУЛЬТАТОВ ---
def merge_results(yandex_tracks, spotify_tracks):
    merged = []
    seen = set()
    
    # Яндекс треки
    for track in yandex_tracks:
        key = f"{track.title.lower()}_{', '.join([a.name for a in track.artists]).lower()}"
        if key not in seen:
            seen.add(key)
            merged.append({'track': track, 'source': 'yandex'})
    
    # Spotify треки
    for item in spotify_tracks:
        key = f"{item['title'].lower()}_{item['artists'].lower()}"
        if key not in seen:
            seen.add(key)
            merged.append({'track': item, 'source': 'spotify'})
    
    return merged

# --- ПОКАЗ ТРЕКА ---
async def show_track(message: types.Message, user_id: int, position: int):
    results = user_search_results.get(user_id, [])
    if not results or position >= len(results):
        await message.answer("❌ Треки закончились!")
        return
    
    item = results[position]
    total = len(results)
    
    # Определяем, что за трек
    if item['source'] == 'yandex':
        track = item['track']
        title = track.title
        artists = ", ".join([a.name for a in track.artists])
        track_id = track.id
        source = 'yandex'
    else:
        track = item['track']
        title = track['title']
        artists = track['artists']
        track_id = track['id']
        source = 'spotify'
    
    # Создаём кнопки
    buttons = []
    
    if source == 'yandex':
        # Трек из Яндекса → можно скачать
        buttons.append([types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track_id}")])
    else:
        # Трек из Spotify → только ссылка
        buttons.append([types.InlineKeyboardButton(text="🎵 Слушать в Spotify", url=track['url'])])
    
    # Навигация
    nav_buttons = []
    if position > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{user_id}_{position-1}"))
    if position < total - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"nav_{user_id}_{position+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([types.InlineKeyboardButton(text=f"📌 {position+1}/{total}", callback_data="ignore")])
    
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Информация об источнике
    source_emoji = "🎧" if source == 'yandex' else "🔵"
    source_text = "Яндекс.Музыка" if source == 'yandex' else "Spotify"
    
    action_text = "скачать" if source == 'yandex' else "открыть в Spotify"
    
    await message.answer(
        f"{source_emoji} **{title}**\n"
        f"👤 **Исполнитель:** {artists}\n"
        f"📡 **Источник:** {source_text}\n"
        f"📌 **Результат {position+1} из {total}**\n\n"
        f"👇 Нажми на кнопку, чтобы {action_text}",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- СКАЧИВАНИЕ ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥 Скачиваю из Яндекс.Музыки...")
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
        minutes, seconds = duration_sec // 60, duration_sec % 60
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
    print(f"✅ Веб-сервер на порту {port}")

# --- МЕНЮ ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="stats", description="📊 Моя статистика"),
        BotCommand(command="top", description="🏆 Топ пользователей"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("✅ Меню команд установлено!")

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def start_command(m: types.Message):
    await m.answer(
        "🎵 **Skibidi_sound** — твой музыкальный помощник!\n\n"
        "📌 **Команды:**\n"
        "/stats — твоя статистика\n"
        "/top — топ пользователей\n\n"
        "🔥 Отправь название трека или исполнителя — я найду музыку в Яндекс.Музыке **и** Spotify!\n"
        "📥 Из Яндекса — скачиваю, из Spotify — даю ссылку на прослушивание.",
        parse_mode="Markdown"
    )

@dp.message(Command("stats"))
async def stats_command(m: types.Message):
    user_id_str = str(m.from_user.id)
    stats = load_stats()
    if user_id_str not in stats:
        await m.answer("📊 У тебя пока нет скачанных треков.")
        return
    user_stats = stats[user_id_str]
    track_count = len(user_stats["tracks"])
    total_sec = track_count * 180
    total_hours, total_min_remain = total_sec // 3600, (total_sec % 3600) // 60
    text = (
        f"📊 **Твоя статистика**\n\n"
        f"🎵 **Скачано:** {user_stats['total_downloads']} треков\n"
        f"🔍 **Поисков:** {user_stats['total_searches']}\n"
        f"⏱ **Прослушано:** {total_hours}ч {total_min_remain}мин\n"
        f"📅 **Первый раз:** {datetime.fromisoformat(user_stats['first_seen']).strftime('%d.%m.%Y')}\n"
    )
    if user_stats["tracks"]:
        text += "\n📋 **Последние:**\n"
        for i, track in enumerate(user_stats["tracks"][-5:], 1):
            text += f"{i}. {track['artist']} — {track['title']}\n"
    await m.answer(text, parse_mode="Markdown")

@dp.message(Command("top"))
async def top_command(m: types.Message):
    top_users = get_top_users()
    if not top_users:
        await m.answer("📊 Пока нет статистики.")
        return
    text = "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ**\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (user_id, data) in enumerate(top_users, 1):
        try:
            user = await bot.get_chat(int(user_id))
            name = user.first_name or user.username or "Аноним"
        except:
            name = "Аноним"
        text += f"{medals[i-1]} **{name}**\n   📥 Скачано: {data['total_downloads']} треков\n\n"
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text)
async def search_command(m: types.Message):
    if m.text.startswith('/'): 
        return
    
    update_search(m.from_user.id)
    
    # --- ПРОВЕРКА НА SPOTIFY ССЫЛКУ ---
    if "open.spotify.com" in m.text and "/track/" in m.text:
        # Если это ссылка на Spotify — ищем в Яндексе
        await m.answer("🔍 Ищу этот трек в Яндекс.Музыке...")
        
        # Парсим ID из ссылки
        match = re.search(r'track/([a-zA-Z0-9]+)', m.text)
        if match:
            spotify_id = match.group(1)
            if sp:
                try:
                    track_info = sp.track(spotify_id)
                    track_name = track_info['name']
                    artist_name = track_info['artists'][0]['name']
                    
                    # Ищем в Яндексе
                    res = yandex_client.search(f"{track_name} {artist_name}", type_='track')
                    if res.tracks:
                        track = res.tracks.results[0]
                        user_id = m.from_user.id
                        user_search_results[user_id] = [{'track': track, 'source': 'yandex'}]
                        user_current_position[user_id] = 0
                        await show_track(m, user_id, 0)
                    else:
                        # Если нет в Яндексе — даём ссылку на Spotify
                        await m.answer(
                            f"🔵 **{track_name}**\n"
                            f"👤 **Исполнитель:** {artist_name}\n\n"
                            f"❌ Не найден в Яндекс.Музыке.\n"
                            f"🎵 Слушай в Spotify: {m.text}",
                            parse_mode="Markdown",
                            reply_markup=types.InlineKeyboardMarkup(
                                inline_keyboard=[[
                                    types.InlineKeyboardButton(text="🎵 Открыть в Spotify", url=m.text)
                                ]]
                            )
                        )
                except Exception as e:
                    await m.answer(f"❌ Ошибка: {str(e)}")
            else:
                await m.answer("❌ Spotify не подключён.")
        return
    
    # --- ОБЫЧНЫЙ ПОИСК ---
    # Ищем в Яндекс.Музыке
    yandex_results = []
    try:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            yandex_results = res.tracks.results[:10]
    except Exception as e:
        print(f"Яндекс ошибка: {e}")
    
    # Ищем в Spotify
    spotify_results = []
    if sp:
        spotify_results = search_spotify(m.text, limit=5)
    
    # Объединяем результаты
    merged = merge_results(yandex_results, spotify_results)
    
    if not merged:
        await m.answer("❌ Ничего не найдено ни в Яндекс.Музыке, ни в Spotify.")
        return
    
    user_id = m.from_user.id
    user_search_results[user_id] = merged
    user_current_position[user_id] = 0
    await show_track(m, user_id, 0)

@dp.callback_query(F.data.startswith("down_"))
async def download_callback(c: types.CallbackQuery):
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
    await set_commands()
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())

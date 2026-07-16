import sys
import os
import json
import asyncio
import requests
import zipfile
import io
import random
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

# --- ХРАНИЛИЩЕ РЕЗУЛЬТАТОВ ПОИСКА ---
user_search_results = {}
user_current_position = {}
playlist_counter = 1

# --- ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ---
def load_data():
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": JSONBIN_API_KEY, "X-Bin-Private": "false"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            record = data.get("record", {})
            return record
        return {}
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return {}

def save_data(data):
    try:
        url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
        headers = {"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json", "X-Bin-Private": "false"}
        response = requests.put(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Данные сохранены в JSONBin")
        else:
            print(f"❌ Ошибка сохранения: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# --- ФУНКЦИИ ДЛЯ ПЛЕЙЛИСТОВ ---
def get_playlists_data():
    data = load_data()
    if "playlists" not in data:
        data["playlists"] = {}
        data["playlist_counter"] = 1
    return data

def save_playlists_data(data):
    save_data(data)

def create_playlist(chat_id, creator_id, name):
    data = get_playlists_data()
    playlist_id = data.get("playlist_counter", 1)
    
    data["playlists"][str(playlist_id)] = {
        "name": name,
        "chat_id": chat_id,
        "creator": creator_id,
        "tracks": [],
        "created": datetime.now().isoformat(),
        "likes": 0
    }
    data["playlist_counter"] = playlist_id + 1
    save_playlists_data(data)
    return playlist_id

def add_track_to_playlist(playlist_id, track_id, track_title, track_artist, added_by):
    data = get_playlists_data()
    playlist_id_str = str(playlist_id)
    
    if playlist_id_str not in data["playlists"]:
        return None
    
    track = {
        "track_id": track_id,
        "title": track_title,
        "artist": track_artist,
        "added_by": added_by,
        "added_at": datetime.now().isoformat(),
        "likes": 0
    }
    
    data["playlists"][playlist_id_str]["tracks"].append(track)
    save_playlists_data(data)
    return track

def get_playlist(playlist_id):
    data = get_playlists_data()
    playlist_id_str = str(playlist_id)
    return data["playlists"].get(playlist_id_str)

def get_playlists_in_chat(chat_id):
    data = get_playlists_data()
    result = []
    for pid, playlist in data["playlists"].items():
        if playlist["chat_id"] == chat_id:
            result.append((pid, playlist))
    return result

def like_track(playlist_id, track_index):
    data = get_playlists_data()
    playlist_id_str = str(playlist_id)
    
    if playlist_id_str not in data["playlists"]:
        return False
    
    tracks = data["playlists"][playlist_id_str]["tracks"]
    if track_index < 0 or track_index >= len(tracks):
        return False
    
    tracks[track_index]["likes"] += 1
    save_playlists_data(data)
    return True

def remove_track(playlist_id, track_index, user_id):
    data = get_playlists_data()
    playlist_id_str = str(playlist_id)
    
    if playlist_id_str not in data["playlists"]:
        return False, "Плейлист не найден"
    
    playlist = data["playlists"][playlist_id_str]
    
    # Только создатель может удалять
    if playlist["creator"] != user_id:
        return False, "❌ Только создатель плейлиста может удалять треки"
    
    tracks = playlist["tracks"]
    if track_index < 0 or track_index >= len(tracks):
        return False, "❌ Трек не найден"
    
    removed = tracks.pop(track_index)
    save_playlists_data(data)
    return True, f"✅ Трек '{removed['title']}' удалён"

# --- ПОИСК ПО ИСПОЛНИТЕЛЮ ---
def search_tracks_by_artist(artist_name):
    try:
        result = yandex_client.search(artist_name, type_='track')
        if result.tracks:
            return result.tracks.results[:5]
        return []
    except Exception as e:
        print(f"❌ Ошибка поиска по исполнителю: {e}")
        return []

# --- ФУНКЦИЯ ДЛЯ ПОКАЗА ТРЕКА ---
async def show_track(message: types.Message, user_id: int, position: int):
    results = user_search_results.get(user_id, [])
    if not results or position >= len(results):
        await message.answer("❌ Треки закончились!")
        return
    
    track = results[position]
    total = len(results)
    artists = ", ".join([a.name for a in track.artists])
    
    buttons = [
        [types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")]
    ]
    
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
        f"🎵 **{track.title}**\n"
        f"👤 **Исполнитель:** {artists}\n"
        f"📌 **Результат {position+1} из {total}**\n\n"
        f"👇 Нажми на кнопку, чтобы скачать",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- СКАЧИВАНИЕ ---
async def download_and_send(message: types.Message, track_id: str, from_playlist=False):
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
            f"🔥 {track_title}\n"
            f"🎤 Исполнитель: {artists}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"💿 Размер: {size_str}\n\n"
            f"🎧 Skibidi_sound бахает для тебя!"
        )
        
        # Создаём кнопки для добавления в плейлист
        buttons = [
            [types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track_id}")],
            [types.InlineKeyboardButton(text="➕ Добавить в плейлист", callback_data=f"add_to_playlist_{track_id}")]
        ]
        
        # Если это не из плейлиста, кнопки будут другие
        if not from_playlist:
            buttons = [
                [types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track_id}")],
                [types.InlineKeyboardButton(text="➕ Добавить в плейлист", callback_data=f"add_to_playlist_{track_id}")]
            ]
        
        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer_audio(
            audio=types.FSInputFile(f_name),
            thumbnail=types.FSInputFile(c_name) if os.path.exists(c_name) else None,
            title=track_title,
            performer=artists,
            caption=caption,
            reply_markup=reply_markup
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

# --- МЕНЮ КОМАНД ---
async def set_commands():
    commands = [
        BotCommand(command="лосяра", description="🦌 Зови лосяру!"),
        BotCommand(command="создать_плейлист", description="🎵 Создать новый плейлист"),
        BotCommand(command="плейлист", description="📋 Посмотреть плейлист"),
        BotCommand(command="плейлисты", description="📋 Все плейлисты в чате"),
        BotCommand(command="лайк", description="❤️ Лайкнуть трек в плейлисте"),
        BotCommand(command="добавить_в_плейлист", description="➕ Добавить трек в плейлист"),
        BotCommand(command="удалить_из_плейлиста", description="❌ Удалить трек из плейлиста"),
        BotCommand(command="случайный", description="🎲 Случайный трек"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("✅ Меню команд установлено!")

# --- КОМАНДЫ ---

# --- /ЛОСЯРА (СТАРТ) ---
@dp.message(Command("лосяра"))
async def losyara_command(m: types.Message):
    await m.answer(
        "🦌 **ЛОСЯРА ПРИШЁЛ!** \n\n"
        "🎵 **Skibidi_sound** — твой музыкальный помощник!\n\n"
        "📌 **Команды:**\n"
        "/лосяра — позвать лосяру\n"
        "/создать_плейлист Название — создать новый плейлист\n"
        "/плейлист ID — посмотреть плейлист\n"
        "/плейлисты — все плейлисты в чате\n"
        "/добавить_в_плейлист ID ссылка_на_трек — добавить трек\n"
        "/удалить_из_плейлиста ID номер_трека — удалить трек\n"
        "/лайк ID номер_трека — лайкнуть трек\n"
        "/случайный — случайный трек\n\n"
        "🔥 Отправь название трека или исполнителя, и я найду музыку!",
        parse_mode="Markdown"
    )

@dp.message(Command("start"))
async def start_command(m: types.Message):
    await losyara_command(m)

# --- /СЛУЧАЙНЫЙ ---
@dp.message(Command("случайный"))
async def random_track_command(m: types.Message):
    await m.answer("🎲 Ищу случайный трек...")
    try:
        # Ищем популярные треки
        res = yandex_client.search("популярное", type_='track')
        if res.tracks:
            track = random.choice(res.tracks.results)
            await download_and_send(m, track.id)
        else:
            await m.answer("❌ Не нашёл ни одного трека")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)}")

# --- /СОЗДАТЬ_ПЛЕЙЛИСТ ---
@dp.message(Command("создать_плейлист"))
async def create_playlist_command(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.answer("❌ Напиши название плейлиста:\n`/создать_плейлист Мои хиты`", parse_mode="Markdown")
        return
    
    name = args[1].strip()
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    playlist_id = create_playlist(chat_id, user_id, name)
    await m.answer(
        f"🎵 **Плейлист создан!**\n\n"
        f"📌 **Название:** {name}\n"
        f"🆔 **ID:** {playlist_id}\n"
        f"👤 **Создатель:** {m.from_user.first_name}\n\n"
        f"➕ Добавить трек: `/добавить_в_плейлист {playlist_id} ссылка_на_трек`\n"
        f"📋 Посмотреть: `/плейлист {playlist_id}`",
        parse_mode="Markdown"
    )

# --- /ПЛЕЙЛИСТ ---
@dp.message(Command("плейлист"))
async def show_playlist_command(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.answer("❌ Укажи ID плейлиста:\n`/плейлист 42`", parse_mode="Markdown")
        return
    
    try:
        playlist_id = int(args[1].strip())
    except:
        await m.answer("❌ ID должен быть числом")
        return
    
    playlist = get_playlist(playlist_id)
    if not playlist:
        await m.answer("❌ Плейлист не найден")
        return
    
    tracks = playlist["tracks"]
    text = (
        f"🎵 **{playlist['name']}**\n"
        f"🆔 **ID:** {playlist_id}\n"
        f"👤 **Создатель:** {playlist['creator']}\n"
        f"📊 **Треков:** {len(tracks)}\n\n"
    )
    
    if not tracks:
        text += "📭 Плейлист пуст. Добавь первый трек!"
    else:
        for i, track in enumerate(tracks, 1):
            likes = "❤️" + "❤️" * min(track.get("likes", 0), 5)
            text += f"{i}. **{track['title']}** — {track['artist']} {likes}\n"
    
    await m.answer(text, parse_mode="Markdown")

# --- /ПЛЕЙЛИСТЫ (все в чате) ---
@dp.message(Command("плейлисты"))
async def list_playlists_command(m: types.Message):
    chat_id = m.chat.id
    playlists = get_playlists_in_chat(chat_id)
    
    if not playlists:
        await m.answer("📭 В этом чате нет плейлистов. Создай первый!")
        return
    
    text = "📋 **Плейлисты в этом чате:**\n\n"
    for pid, playlist in playlists:
        track_count = len(playlist["tracks"])
        text += f"🆔 {pid}: **{playlist['name']}** ({track_count} треков)\n"
    
    await m.answer(text, parse_mode="Markdown")

# --- /ДОБАВИТЬ_В_ПЛЕЙЛИСТ ---
@dp.message(Command("добавить_в_плейлист"))
async def add_to_playlist_command(m: types.Message):
    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        await m.answer("❌ Использование:\n`/добавить_в_плейлист ID ссылка_на_трек`\n\nИли отправь трек текстом после команды.", parse_mode="Markdown")
        return
    
    try:
        playlist_id = int(args[1])
    except:
        await m.answer("❌ ID должен быть числом")
        return
    
    track_query = args[2].strip()
    
    # Ищем трек
    res = yandex_client.search(track_query, type_='track')
    if not res.tracks:
        await m.answer("❌ Трек не найден")
        return
    
    track = res.tracks.results[0]
    track_id = track.id
    track_title = track.title
    track_artist = ", ".join([a.name for a in track.artists])
    
    result = add_track_to_playlist(playlist_id, track_id, track_title, track_artist, m.from_user.id)
    if result is None:
        await m.answer("❌ Плейлист не найден")
        return
    
    await m.answer(
        f"✅ **Трек добавлен!**\n\n"
        f"🎵 {track_title} — {track_artist}\n"
        f"📌 В плейлист: ID {playlist_id}\n"
        f"👤 Добавил: {m.from_user.first_name}",
        parse_mode="Markdown"
    )

# --- /УДАЛИТЬ_ИЗ_ПЛЕЙЛИСТА ---
@dp.message(Command("удалить_из_плейлиста"))
async def remove_from_playlist_command(m: types.Message):
    args = m.text.split()
    if len(args) < 3:
        await m.answer("❌ Использование:\n`/удалить_из_плейлиста ID номер_трека`", parse_mode="Markdown")
        return
    
    try:
        playlist_id = int(args[1])
        track_index = int(args[2]) - 1
    except:
        await m.answer("❌ ID и номер должны быть числами")
        return
    
    success, message = remove_track(playlist_id, track_index, m.from_user.id)
    await m.answer(message)

# --- /ЛАЙК ---
@dp.message(Command("лайк"))
async def like_track_command(m: types.Message):
    args = m.text.split()
    if len(args) < 3:
        await m.answer("❌ Использование:\n`/лайк ID номер_трека`", parse_mode="Markdown")
        return
    
    try:
        playlist_id = int(args[1])
        track_index = int(args[2]) - 1
    except:
        await m.answer("❌ ID и номер должны быть числами")
        return
    
    if like_track(playlist_id, track_index):
        await m.answer("❤️ **Ты лайкнул этот трек!**")
    else:
        await m.answer("❌ Трек или плейлист не найден")

# --- ОБРАБОТЧИК ПОИСКА (ТЕКСТ) ---
@dp.message(F.text)
async def handle_search(m: types.Message):
    if m.text.startswith('/'):
        return
    
    res = yandex_client.search(m.text, type_='track')
    if res.tracks:
        user_id = m.from_user.id
        user_search_results[user_id] = res.tracks.results
        user_current_position[user_id] = 0
        await show_track(m, user_id, 0)
    else:
        await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

# --- CALLBACK: СКАЧАТЬ ---
@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer("🔄 Скачиваю...")
    track_id = c.data.replace("down_", "")
    await download_and_send(c.message, track_id)

# --- CALLBACK: НАВИГАЦИЯ ---
@dp.callback_query(F.data.startswith("nav_"))
async def callback_navigation(c: types.CallbackQuery):
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

# --- CALLBACK: ДОБАВИТЬ В ПЛЕЙЛИСТ ---
@dp.callback_query(F.data.startswith("add_to_playlist_"))
async def callback_add_to_playlist(c: types.CallbackQuery):
    track_id = c.data.replace("add_to_playlist_", "")
    
    # Получаем информацию о треке
    try:
        track = yandex_client.tracks([track_id])[0]
        track_title = track.title
        track_artist = ", ".join([a.name for a in track.artists])
        
        # Находим плейлисты пользователя в этом чате
        playlists = get_playlists_in_chat(c.message.chat.id)
        
        if not playlists:
            await c.answer("❌ В этом чате нет плейлистов. Создай первый!", show_alert=True)
            return
        
        # Создаём кнопки для выбора плейлиста
        buttons = []
        for pid, playlist in playlists:
            buttons.append([types.InlineKeyboardButton(
                text=f"📌 {playlist['name']} (ID: {pid})",
                callback_data=f"add_to_playlist_confirm_{pid}_{track_id}"
            )])
        
        buttons.append([types.InlineKeyboardButton(text="❌ Отмена", callback_data="ignore")])
        
        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await c.message.answer(
            f"🎵 **Выбери плейлист для добавления:**\n\n"
            f"Трек: {track_title} — {track_artist}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await c.answer()
    except Exception as e:
        await c.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

# --- CALLBACK: ПОДТВЕРЖДЕНИЕ ДОБАВЛЕНИЯ В ПЛЕЙЛИСТ ---
@dp.callback_query(F.data.startswith("add_to_playlist_confirm_"))
async def callback_add_to_playlist_confirm(c: types.CallbackQuery):
    parts = c.data.split("_")
    playlist_id = int(parts[3])
    track_id = parts[4]
    
    try:
        track = yandex_client.tracks([track_id])[0]
        track_title = track.title
        track_artist = ", ".join([a.name for a in track.artists])
        
        result = add_track_to_playlist(playlist_id, track_id, track_title, track_artist, c.from_user.id)
        if result is None:
            await c.answer("❌ Плейлист не найден", show_alert=True)
            return
        
        await c.answer("✅ Трек добавлен в плейлист!")
        await c.message.edit_text(
            f"✅ **Трек добавлен!**\n\n"
            f"🎵 {track_title} — {track_artist}\n"
            f"📌 В плейлист: ID {playlist_id}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await c.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "ignore")
async def ignore_callback(c: types.CallbackQuery):
    await c.answer()
    try:
        await c.message.delete()
    except:
        pass

# --- ГЛАВНАЯ ---
async def main():
    await set_commands()
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())

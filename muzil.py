import sys
import os
import json
import asyncio
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
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
TELEGRAM_TOKEN = "8632244991:AAE58ZHOF3_TbNNlXhmHjTaSRBim1gBByQo" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- СТАТИСТИКА ---
STATS_FILE = "stats.json"

def load_stats():
    """Загружает статистику из файла"""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_stats(stats):
    """Сохраняет статистику в файл"""
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def update_stats(user_id, track_title, artist_name):
    """Обновляет статистику пользователя"""
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
    """Обновляет количество поисков"""
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
    """Возвращает топ-5 пользователей по скачиваниям"""
    stats = load_stats()
    if not stats:
        return []
    
    sorted_users = sorted(
        stats.items(),
        key=lambda x: x[1]["total_downloads"],
        reverse=True
    )[:5]
    
    return sorted_users

# --- ЛОГИКА СКАЧИВАНИЯ С КРАСИВЫМ ОФОРМЛЕНИЕМ ---
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

# --- ВЕБ-СЕРВЕР ДЛЯ UPTIME ROBOT ---
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

# --- ОБРАБОТЧИКИ ---

# 1. Обработчик команды /start
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

# 2. Обработчик команды /stats
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

# 3. Обработчик команды /top
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

# 4. Обработчик текстовых сообщений (поиск треков)
@dp.message(F.text)
async def handle_search(m: types.Message):
    # ПРОВЕРЯЕМ: если это команда (начинается с /) - игнорируем
    if m.text.startswith('/'):
        return
    
    update_search(m.from_user.id)
    
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
    else:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            track = res.tracks.results[0]
            await m.answer(
                f"✅ Нашел трек!\n\n"
                f"🎵 {track.title} — {track.artists[0].name}\n"
                f"👇 Нажми на кнопку, чтобы скачать",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[
                        types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")
                    ]]
                )
            )
        else:
            await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

# 5. Обработчик callback-запросов (кнопки)
@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer("🔽 Начинаю загрузку...")
    await download_and_send(c.message, c.data.split("_")[1])

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())

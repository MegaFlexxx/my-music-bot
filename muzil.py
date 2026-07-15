import sys
import os
import asyncio
import sqlite3
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from aiohttp import web

# --- 1. ПАТЧ ---
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

# --- 2. БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
                      (user_id INTEGER, title TEXT, artist TEXT)''')
    conn.commit()
    conn.close()

def add_to_history(user_id, title, artist):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history VALUES (?, ?, ?)", (user_id, title, artist))
    conn.commit()
    conn.close()

init_db()

# --- 3. КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGWwhTLEDM_nxFzbnmkWMGym3pNd3weS-M" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- 4. ЛОГИКА ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        add_to_history(message.from_user.id, track.title, ", ".join([a.name for a in track.artists]))
        
        # Генерация описания
        genre = track.genres[0] if track.genres else "музыка"
        caption = f"🎵 *{track.title}*\n👤 Исполнитель: {', '.join([a.name for a in track.artists])}\n🏷 Жанр: {genre.capitalize()}\n\n*Бот Skibidi_sound рекомендует!*"
        
        info = track.get_download_info()
        link = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: f.write(requests.get(link, timeout=15).content)
        
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_cover_url = cover_url if cover_url.startswith('http') else "https:" + cover_url
            with open(c_name, 'wb') as f: f.write(requests.get(full_cover_url, timeout=10).content)
            Image.open(c_name).convert('RGB').resize((400, 400)).save(c_name, "JPEG", quality=85)
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: audio.add_tags(ID3=ID3)
            with open(c_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
            audio.save(v2_version=3)

        await message.answer_audio(
            audio=types.FSInputFile(f_name), 
            thumbnail=types.FSInputFile(c_name) if os.path.exists(c_name) else None,
            title=track.title,
            performer=", ".join([a.name for a in track.artists]),
            caption=caption,
            parse_mode="Markdown"
        )
        for f in [f_name, c_name]: 
            if os.path.exists(f): os.remove(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- 5. ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Я — Skibidi_sound. Пиши название трека, а по команде /history увидишь свои последние скачивания.")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, artist FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT 5", (m.from_user.id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows: await m.answer("История пуста.")
    else: await m.answer("🕒 Последние треки:\n" + "\n".join([f"- {r[0]} ({r[1]})" for r in rows]))

@dp.message(F.text)
async def handle_search(m: types.Message):
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
    else:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            track = res.tracks.results[0]
            await m.answer(f"✅ Нашел: {track.title} — {track.artists[0].name}", 
                           reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]]))

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer()
    await download_and_send(c.message, c.data.split("_")[1])

# --- 6. ЗАПУСК ---
async def handle(request): return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

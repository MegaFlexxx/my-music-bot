import os
import logging
import sys

# --- 1. ПАТЧ ДЛЯ YANDEX_MUSIC ---
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

# --- 2. ИМПОРТЫ ---
import asyncio
import aiohttp
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1
from aiohttp import web
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- 3. НАСТРОЙКИ СЕТИ ---
def get_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

# --- 4. КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8971955986:AAGnslgWHWBv8SS4yjH7tw-Bnmzs104Plus"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- 5. ВЕБ-СЕРВЕР ---
async def handle(request): return web.Response(text="Бот работает!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()

async def download_and_send(message: types.Message, track_id: str):
    status_msg = await message.answer("📥 Готовлю файл...")
    try:
        track = yandex_client.tracks([track_id])[0]
        file_name, cover_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        
        response = get_session().get(best_info.get_direct_link(), timeout=15)
        with open(file_name, 'wb') as f: f.write(response.content)
        
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            try:
                img_resp = get_session().get("https:" + cover_url, timeout=10)
                with open(cover_name, 'wb') as f: f.write(img_resp.content)
                with Image.open(cover_name) as img: img.convert('RGB').resize((400, 400)).save(cover_name, "JPEG", quality=85)
            except: 
                if os.path.exists(cover_name): os.remove(cover_name)
        
        audio = MP3(file_name, ID3=ID3)
        if audio.tags is None: audio.add_tags(ID3=ID3)
        audio.tags.delall('APIC'); audio.tags.add(TIT2(encoding=3, text=track.title))
        audio.tags.add(TPE1(encoding=3, text=", ".join([a.name for a in track.artists])))
        
        if os.path.exists(cover_name):
            with open(cover_name, 'rb') as img: audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
        audio.save(v2_version=3)
        
        thumb = types.FSInputFile(cover_name) if os.path.exists(cover_name) else None
        await message.answer_audio(audio=types.FSInputFile(file_name), thumbnail=thumb)
        
        for f in [file_name, cover_name]: 
            if os.path.exists(f): os.remove(f)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"💥 Ошибка: {str(e)}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message): await message.answer("Привет! Пришли название или ссылку.")

@dp.message(F.text)
async def handle_search(message: types.Message):
    if message.text.startswith("/"): return
    if "music.yandex.ru" in message.text and "/track/" in message.text:
        await download_and_send(message, message.text.split("/track/")[1].split("?")[0]); return
    res = yandex_client.search(message.text, type_='track')
    if res.tracks:
        track = res.tracks.results[0]
        await message.answer(f"✅ {track.title} — {track.artists[0].name}", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]]))
    else: await message.answer("❌ Ничего не нашел.")

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer(); await download_and_send(c.message, c.data.split("_")[1])

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    loop.run_until_complete(dp.start_polling(bot))

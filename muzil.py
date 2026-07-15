import sys

# --- 1. ПАТЧ (ОДИН РАЗ, ДО ВСЕГО) ---
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
import os
import logging
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
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1
from aiohttp import web

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8971955986:AAGnslgWHWBv8SS4yjH7tw-Bnmzs104Plus"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        # Скачивание
        link = sorted(track.get_download_info(), key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: f.write(requests.get(link, timeout=15).content)
        
        # Обложка
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            with open(c_name, 'wb') as f: f.write(requests.get("https:"+cover_url, timeout=10).content)
            img = Image.open(c_name).convert('RGB').resize((400, 400))
            img.save(c_name, "JPEG", quality=85)
            
            # Вшиваем теги
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: audio.add_tags(ID3=ID3)
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=open(c_name, 'rb').read()))
            audio.save(v2_version=3)

        # Отправка с Thumb
        thumb = types.FSInputFile(c_name) if os.path.exists(c_name) else None
        await message.answer_audio(audio=types.FSInputFile(f_name), thumbnail=thumb)
        
        for f in [f_name, c_name]: 
            if os.path.exists(f): os.remove(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# ... (остальные обработчики прежние)
if __name__ == "__main__":
    import threading
    def start_server():
        app = web.Application()
        web.run_app(app, port=int(os.environ.get('PORT', 8080)))
    threading.Thread(target=start_server, daemon=True).start()
    dp.run_polling(bot)

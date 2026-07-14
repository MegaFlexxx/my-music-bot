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

# --- 1. НАСТРОЙКИ СЕТИ ---
def get_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

# --- 2. КОД БОТА ---
TELEGRAM_TOKEN = "8971955986:AAGnslgWHWBv8SS4yjH7tw-Bnmzs104Plus" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

async def download_and_send(message: types.Message, track_id: str):
    status_msg = await message.answer("📥 Готовлю файл...")
    try:
        track = yandex_client.tracks([track_id])[0]
        file_name, cover_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        # Скачивание с сессией, которая умеет прощать сетевые ошибки
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        
        response = get_session().get(best_info.get_direct_link(), timeout=10)
        with open(file_name, 'wb') as f: f.write(response.content)
        
        # Обработка обложки (ресайз до 400x400 и RGB для Telegram)
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            try:
                img_resp = get_session().get("https:" + cover_url, timeout=5)
                with open(cover_name, 'wb') as f: f.write(img_resp.content)
                with Image.open(cover_name) as img: 
                    img.convert('RGB').resize((400, 400)).save(cover_name, "JPEG", quality=85)
            except: pass
        
        # Запись тегов ID3v2.3
        audio = MP3(file_name, ID3=ID3)
        if audio.tags is None: audio.add_tags(ID3=ID3)
        audio.tags.delall('APIC'); audio.tags.add(TIT2(encoding=3, text=track.title))
        audio.tags.add(TPE1(encoding=3, text=", ".join([a.name for a in track.artists])))
        
        if os.path.exists(cover_name):
            with open(cover_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
        audio.save(v2_version=3)
        
        # ОТПРАВКА С THUMBNAIL (чтобы видеть картинку в списке)
        thumb = types.FSInputFile(cover_name) if os.path.exists(cover_name) else None
        await message.answer_audio(audio=types.FSInputFile(file_name), thumbnail=thumb)
        
        for f in [file_name, cover_name]: 
            if os.path.exists(f): os.remove(f)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"💥 Ошибка: {str(e)}")

# ... (остальные обработчики команд и поиска остаются без изменений)

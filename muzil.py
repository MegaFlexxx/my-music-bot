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

# --- ЗАПЛАТКА ДЛЯ API ---
import yandex_music
if hasattr(yandex_music, 'Product'):
    original_init = yandex_music.Product.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault('common_period_duration', None)
        original_init(self, *args, **kwargs)
    yandex_music.Product.__init__ = patched_init

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8971955986:AAHYy4W3fQEiTE9k-FbZmkfCidOdX0hDBbE" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

async def download_and_send(message: types.Message, track_id: str):
    status_msg = await message.answer("📥 Готовлю файл...")
    try:
        track = yandex_client.tracks([track_id])[0]
        file_name = f"{track_id}.mp3"
        cover_name = f"{track_id}.jpg"
        
        # Скачивание аудио
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        async with aiohttp.ClientSession() as session:
            async with session.get(best_info.get_direct_link()) as resp:
                with open(file_name, 'wb') as f: f.write(await resp.read())
        
        # Скачивание обложки
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_url = "https:" + cover_url if not cover_url.startswith("http") else cover_url
            try:
                img_data = requests.get(full_url, timeout=5).content
                with open(cover_name, 'wb') as f: f.write(img_data)
                Image.open(cover_name).convert('RGB').save(cover_name, "JPEG")
            except: 
                if os.path.exists(cover_name): os.remove(cover_name)
        
        # Теги
        audio = MP3(file_name, ID3=ID3)
        if audio.tags is None: audio.add_tags(ID3=ID3)
        audio.tags.add(TIT2(encoding=3, text=track.title))
        audio.tags.add(TPE1(encoding=3, text=", ".join([a.name for a in track.artists])))
        if os.path.exists(cover_name):
            with open(cover_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, data=img.read()))
        audio.save()
        
        await message.answer_audio(audio=types.FSInputFile(file_name))
        
        for f in [file_name, cover_name]: 
            if os.path.exists(f): os.remove(f)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"💥 Ошибка: {str(e)}")

# Обработчик поиска
@dp.message(F.text)
async def handle_search(message: types.Message):
    if message.text.startswith("/"): return
    search_result = yandex_client.search(message.text, type_='track')
    if search_result.tracks:
        track = search_result.tracks.results[0]
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]
        ])
        await message.answer(f"✅ Нашел: {track.title} — {track.artists[0].name}", reply_markup=kb)
    else:
        await message.answer("❌ Ничего не нашел.")

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(callback: types.CallbackQuery):
    await download_and_send(callback.message, callback.data.split("_")[1])

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))

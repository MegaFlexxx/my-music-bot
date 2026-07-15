import sys
import os
import logging
import asyncio
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

# --- 1. ПАТЧ (ИСПРАВЛЕНИЕ ОШИБКИ YANDEX MUSIC) ---
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

# --- 2. КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGWwhTLEDM_nxFzbnmkWMGym3pNd3weS-M" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- 3. ЛОГИКА СКАЧИВАНИЯ ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        # Скачивание файла
        info = track.get_download_info()
        link = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: f.write(requests.get(link, timeout=15).content)
        
        # Скачивание обложки (Исправлено)
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_cover_url = cover_url if cover_url.startswith('http') else "https:" + cover_url
            with open(c_name, 'wb') as f: 
                f.write(requests.get(full_cover_url, timeout=10).content)
            
            # Обработка картинки
            Image.open(c_name).convert('RGB').resize((400, 400)).save(c_name, "JPEG", quality=85)
            
            # Вшиваем теги
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: audio.add_tags(ID3=ID3)
            with open(c_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
            audio.save(v2_version=3)

        # Отправка
        thumb = types.FSInputFile(c_name) if os.path.exists(c_name) else None
        await message.answer_audio(audio=types.FSInputFile(f_name), thumbnail=thumb)
        
        for f in [f_name, c_name]: 
            if os.path.exists(f): os.remove(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- 4. ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start(m: types.Message): await m.answer("Привет! Пришли название или ссылку.")

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
    await c.answer(); await download_and_send(c.message, c.data.split("_")[1])

# --- 5. ЗАПУСК ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))

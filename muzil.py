import os
import re
import logging
import asyncio
import aiohttp
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, error

# =================== НАСТРОЙКИ ===================
TELEGRAM_TOKEN = "8971955986:AAE8L7Lab3mxnpGAwRwTyGkMpPatRUiJhs0"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
# =================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# Обработчик поиска
@dp.message(F.text)
async def handle_search(message: types.Message):
    text = message.text.strip()
    
    # Если это ссылка, сразу скачиваем, если текст - ищем
    track_re = re.compile(r"track/(\d+)")
    match = track_re.search(text)
    
    if match:
        await download_and_send(message, match.group(1))
    else:
        status_msg = await message.answer("🔍 Ищу...")
        search_result = yandex_client.search(text, type_='track')
        
        if search_result.tracks and search_result.tracks.results:
            track = search_result.tracks.results[0]
            artists = ", ".join([a.name for a in track.artists])
            
            # Кнопка под сообщением
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]
            ])
            await status_msg.edit_text(f"✅ Нашел: *{artists} — {track.title}*", 
                                       reply_markup=kb, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Ничего не нашел.")

# Обработчик нажатия кнопки "Скачать"
@dp.callback_query(F.data.startswith("down_"))
async def callback_download(callback: types.CallbackQuery):
    track_id = callback.data.split("_")[1]
    await callback.answer("Начинаю загрузку...")
    await download_and_send(callback.message, track_id, is_callback=True)

# Функция скачивания (общая для ссылок и кнопок)
async def download_and_send(message: types.Message, track_id: str, is_callback=False):
    status_msg = await message.answer("📥 Готовлю файл...")
    
    try:
        track = yandex_client.tracks([track_id])[0]
        title = track.title
        artists = ", ".join([a.name for a in track.artists])
        file_name = "".join(c for c in f"{artists} - {title}.mp3" if c.isalnum() or c in " -_.").strip()
        cover_name = f"cover_{track_id}.jpg"

        # Скачивание
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.get(best_info.get_direct_link()) as resp:
                with open(file_name, 'wb') as f:
                    f.write(await resp.read())

        # Обложка
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            cover_url = ("https:" + cover_url) if cover_url.startswith('//') else cover_url
            cover_resp = requests.get(cover_url, timeout=10)
            with open(cover_name, 'wb') as f:
                f.write(cover_resp.content)

        # Теги
        audio = MP3(file_name, ID3=ID3)
        try: audio.add_tags()
        except: pass
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artists))
        if os.path.exists(cover_name):
            with open(cover_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
        audio.save()

        # Отправка
        await message.answer_audio(
            audio=types.FSInputFile(file_name),
            title=title, performer=artists,
            thumbnail=types.FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        os.remove(file_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        await status_msg.delete()
        
    except Exception as e:
        logging.error(e)
        await status_msg.edit_text("💥 Ошибка при скачивании.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

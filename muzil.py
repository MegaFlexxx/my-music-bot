import os

# Отключаем использование системных прокси
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

# --- ЗАПЛАТКА ---
import yandex_music
if hasattr(yandex_music, 'Product'):
    original_init = yandex_music.Product.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault('common_period_duration', None)
        original_init(self, *args, **kwargs)
    yandex_music.Product.__init__ = patched_init
# -----------------

import re
import logging
import asyncio
import aiohttp
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
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

# Клавиатура
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти трек"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я твой музыкальный бот. Используй кнопки или просто напиши название песни!",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🔍 Найти трек")
async def ask_search(message: types.Message):
    await message.answer("Просто напиши название песни или исполнителя, и я её найду!")

@dp.message(F.text == "ℹ️ Помощь")
async def ask_help(message: types.Message):
    await message.answer("Я умею скачивать треки с Яндекс Музыки. Просто пришли название песни или ссылку на неё.")

@dp.message(F.text & ~F.text.in_({"🔍 Найти трек", "ℹ️ Помощь"}))
async def handle_message(message: types.Message):
    query = message.text.strip()
    track_re = re.compile(r"track/(\d+)")
    match = track_re.search(query)
    
    track_id = None
    status_msg = await message.answer("🔍 Ищу...")

    try:
        if match:
            track_id = match.group(1)
        else:
            search_result = yandex_client.search(query, type_='track')
            if search_result.tracks and search_result.tracks.results:
                track_id = search_result.tracks.results[0].id
            else:
                await status_msg.edit_text("❌ К сожалению, ничего не нашлось.")
                return

        tracks = yandex_client.tracks([track_id])
        track = tracks[0]
        title = track.title
        artists = ", ".join([artist.name for artist in track.artists])
        file_name = "".join(c for c in f"{artists} - {title}.mp3" if c.isalnum() or c in " -_.").strip()
        cover_name = f"cover_{track_id}.jpg"

        await status_msg.edit_text(f"📥 Скачиваю: {artists} — {title}")

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
            title=title,
            performer=artists,
            thumbnail=types.FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        os.remove(file_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        await status_msg.delete()

    except Exception as e:
        logging.error(e)
        await status_msg.edit_text("💥 Произошла ошибка. Попробуй еще раз.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

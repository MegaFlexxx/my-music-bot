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
from mutagen.id3 import ID3, APIC, TIT2, TPE1

# =================== НАСТРОЙКИ ===================
TELEGRAM_TOKEN = "8971955986:AAE8L7Lab3mxnpGAwRwTyGkMpPatRUiJhs0"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
CHANNEL_ID = -1001745381023 # Твой ID канала
# =================================================

# --- ЗАПЛАТКА ДЛЯ YANDEX MUSIC ---
import yandex_music
if hasattr(yandex_music, 'Product'):
    original_init = yandex_music.Product.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault('common_period_duration', None)
        original_init(self, *args, **kwargs)
    yandex_music.Product.__init__ = patched_init

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member', 'restricted']
    except:
        return False

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я твой музыкальный бот. Просто напиши название песни для поиска.")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("🛠 Используй бота для поиска музыки. Нужно быть подписанным на канал!")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.answer("✅ Бот онлайн!")

# --- ОСНОВНОЙ ОБРАБОТЧИК ---
@dp.message(F.text & ~F.text.startswith("/"))
async def handle_search(message: types.Message):
    # Проверка подписки
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/shkibidi_gang")]
        ])
        await message.answer("⚠️ Для использования бота нужно подписаться на наш канал!", reply_markup=kb)
        return

    text = message.text.strip()
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
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]
            ])
            await status_msg.edit_text(f"✅ Нашел: *{artists} — {track.title}*", reply_markup=kb, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Ничего не нашел.")

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(callback: types.CallbackQuery):
    track_id = callback.data.split("_")[1]
    await callback.answer("Начинаю загрузку...")
    await download_and_send(callback.message, track_id)

# --- ФУНКЦИЯ СКАЧИВАНИЯ ---
async def download_and_send(message: types.Message, track_id: str):
    status_msg = await message.answer("📥 Готовлю файл...")
    try:
        track = yandex_client.tracks([track_id])[0]
        title = track.title
        artists = ", ".join([a.name for a in track.artists])
        file_name = f"{artists} - {title}.mp3".replace("/", "_")
        cover_name = f"cover_{track_id}.jpg"
        
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(best_info.get_direct_link()) as resp:
                with open(file_name, 'wb') as f: f.write(await resp.read())
        
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            with open(cover_name, 'wb') as f: f.write(requests.get("https:" + cover_url).content)
        
        audio = MP3(file_name, ID3=ID3)
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artists))
        if os.path.exists(cover_name):
            with open(cover_name, 'rb') as img: audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, data=img.read()))
        audio.save()
        
        await message.answer_audio(audio=types.FSInputFile(file_name), title=title, performer=artists)
        os.remove(file_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text("💥 Ошибка.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import os
import re
import logging
import asyncio
import aiohttp
import requests
from PIL import Image  # Добавляем для конвертации обложек
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1

# =================== НАСТРОЙКИ ===================
TELEGRAM_TOKEN = "8971955986:AAHcJC4WSRqp0aMzBmt0lZjVk1VRMOzNl-g"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
CHANNEL_ID = -1001745381023 
# =================================================

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

async def is_subscribed(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member', 'restricted']
    except:
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я твой музыкальный бот, а мой создатель очень красивый парень. Используй меню команд или просто напиши название песни для поиска.")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("🛠 **Как пользоваться ботом:**\n\n1. Просто напиши название трека или исполнителя.\n2. Я найду результат.\n3. Нажми «📥 Скачать».\n\nЕсли совсем все плохо, пиши в поддержку: @serhf_bot_helper", parse_mode="Markdown", disable_web_page_preview=True)

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_search(message: types.Message):
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Подписаться", url="https://t.me/shkibidi_gang")], [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]])
        await message.answer("⚠️ Для использования бота нужно подписаться на канал:", reply_markup=kb)
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
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Скачать", callback_data=f"down_{track.id}")]])
            await status_msg.edit_text(f"✅ Нашел: *{artists} — {track.title}*", reply_markup=kb, parse_mode="Markdown")
        else:
            await status_msg.edit_text("❌ Ничего не нашел.")

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
        has_cover = False
        if cover_url:
            full_url = cover_url if cover_url.startswith("http") else "https:" + cover_url
            try:
                img_data = requests.get(full_url, timeout=10).content
                with open(cover_name, 'wb') as f: f.write(img_data)
                # Конвертация в RGB для совместимости с MP3
                img = Image.open(cover_name).convert('RGB')
                img.save(cover_name, "JPEG")
                has_cover = True
            except: pass
        
        audio = MP3(file_name, ID3=ID3)
        if audio.tags is None: audio.add_tags(ID3=ID3)
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artists))
        if has_cover:
            with open(cover_name, 'rb') as img: 
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, data=img.read()))
        audio.save()
        
        await message.answer_audio(audio=types.FSInputFile(file_name), title=title, performer=artists)
        for f in [file_name, cover_name]: 
            if os.path.exists(f): os.remove(f)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"💥 Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))

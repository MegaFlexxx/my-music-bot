import asyncio
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGSj6V48pH9xz2S5sAIGVj96N52M2pcgPg" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# --- 1. ОБРАБОТЧИК КОМАНД (они должны быть выше обработчика текста) ---
@dp.message(Command("start"))
async def start_handler(m: types.Message):
    await m.answer("Привет! Пришли название трека или ссылку, и я пришлю его аудиофайлом с обложкой.")

# --- 2. УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТА ---
@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    status_msg = await m.answer("🔍 Ищу...")
    
    try:
        query = m.text.strip()
        track_id_match = re.search(r'track/(\d+)', query)
        track = None
        
        if track_id_match:
            track = yandex_client.tracks([track_id_match.group(1)])[0]
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if not track:
            return await status_msg.edit_text("❌ Ничего не нашел.")

        audio_name = f"{track.id}.mp3"
        cover_name = f"{track.id}.jpg"
        
        track.download(audio_name)
        if track.cover_uri:
            track.download_cover(cover_name, size='200x200')
            
        await m.answer_audio(
            audio=FSInputFile(audio_name),
            caption=f"✅ {track.title} — {', '.join([a.name for a in track.artists])}",
            title=track.title,
            performer=', '.join([a.name for a in track.artists]),
            thumbnail=FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        
        await status_msg.delete()
        if os.path.exists(audio_name): os.remove(audio_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- ЗАПУСК ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

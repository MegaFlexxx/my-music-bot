import asyncio
import asyncpg
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGSj6V48pH9xz2S5sAIGVj96N52M2pcgPg" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
DATABASE_URL = "postgresql://postgres.plqrkoszdqnxaghcshik:Fortnite_123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# --- ФУНКЦИИ БД ---
async def add_to_db(user_id, title, track_id="0"):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
                           user_id, title, str(track_id))
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

# --- ОБРАБОТЧИК ---
@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    msg = await m.answer("🔍 Ищу и готовлю файл...")
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
            return await msg.edit_text("❌ Ничего не нашел.")
        
        # Подготовка файлов
        audio_name = f"{track.id}.mp3"
        cover_name = f"{track.id}.jpg"
        
        # Скачивание
        track.download(audio_name)
        if track.cover_uri:
            track.download_cover(cover_name, size='200x200')
            
        # Отправка аудио с метаданными
        await m.answer_audio(
            audio=FSInputFile(audio_name),
            caption=f"✅ Нашел: {track.title} — {', '.join([a.name for a in track.artists])}\nБот Skibidi_sound рекомендует!",
            title=track.title,
            performer=', '.join([a.name for a in track.artists]),
            thumbnail=FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        
        # Запись в БД и удаление
        await add_to_db(m.from_user.id, f"{track.title} — {track.artists[0].name}", track.id)
        os.remove(audio_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): await m.answer("Привет! Пришли название или ссылку.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import asyncpg
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
# Замените на ваши реальные токены и URL базы данных
TELEGRAM_TOKEN = "8632244991:AAFUepxkOy7nv_jVqgCD8cl4qceYc_fxoyA" 
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

# --- ОБРАБОТЧИК ПОИСКА И ОТПРАВКИ ФАЙЛА ---
@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    msg = await m.answer("🔍 Ищу и готовлю файл...")
    try:
        query = m.text.strip()
        
        # Регулярное выражение для поиска ID трека в ссылке
        track_id_match = re.search(r'track/(\d+)', query)
        
        track = None
        
        if track_id_match:
            # Если найдена ссылка, получаем трек по ID
            track_id = track_id_match.group(1)
            tracks_res = yandex_client.tracks([track_id])
            if tracks_res:
                track = tracks_res[0]
        else:
            # Иначе выполняем текстовый поиск
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if not track:
            return await msg.edit_text("❌ Ничего не нашел.")
        
        # Подготовка имен файлов
        base_file_name = f"{track.title}_{track.artists[0].name}"
        audio_file_name = f"{base_file_name}.mp3"
        cover_file_name = f"{base_file_name}.jpg"
        
        # Скачиваем трек
        track.download(audio_file_name)
        
        # Скачиваем обложку (если есть)
        if track.cover_uri:
            track.download_cover(cover_file_name)
        
        # Подготовка аудиофайла
        audio = FSInputFile(audio_file_name)
        
        # Отправляем аудиофайл с обложкой
        await m.answer_audio(
            audio=audio, 
            caption=f"✅ Нашел: {track.title} — {', '.join([a.name for a in track.artists])}\nБот Skibidi_sound рекомендует!",
            thumbnail=FSInputFile(cover_file_name) if track.cover_uri else None # Прикрепляем обложку
        )
        
        # Запись в БД
        await add_to_db(m.from_user.id, f"{track.title} — {track.artists[0].name}", track.id)
        
        # Удаление временных файлов
        os.remove(audio_file_name)
        if track.cover_uri and os.path.exists(cover_file_name):
            os.remove(cover_file_name)
            
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"Ошибка при обработке: {e}")
        # Очистка в случае ошибки
        if 'audio_file_name' in locals() and os.path.exists(audio_file_name):
            os.remove(audio_file_name)
        if 'cover_file_name' in locals() and os.path.exists(cover_file_name):
            os.remove(cover_file_name)

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Пришли название трека или ссылку на него в Яндекс.Музыке, и я пришлю его аудиофайлом с обложкой.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

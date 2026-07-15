import asyncio
import asyncpg
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
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
        res = yandex_client.search(query, type_='track')
        
        if not res.tracks or not res.tracks.results:
            return await msg.edit_text("❌ Ничего не нашел.")
        
        track = res.tracks.results[0]
        file_name = f"{track.title}.mp3"
        
        # Скачиваем трек
        track.download(file_name)
        
        # Отправляем аудиофайл
        audio = FSInputFile(file_name)
        await m.answer_audio(
            audio=audio, 
            caption=f"✅ Нашел: {track.title} — {', '.join([a.name for a in track.artists])}\nБот Skibidi_sound рекомендует!"
        )
        
        # Запись в БД и удаление временного файла
        await add_to_db(m.from_user.id, f"{track.title} — {track.artists[0].name}", track.id)
        os.remove(file_name)
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"Ошибка при обработке: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Пришли название трека, и я пришлю его аудиофайлом.")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT artist_name FROM subscriptions1 WHERE user_id = $1 ORDER BY id DESC LIMIT 5", m.from_user.id)
    await conn.close()
    await m.answer("🕒 Последние:\n" + "\n".join([f"- {r['artist_name']}" for r in rows]) if rows else "История пуста.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

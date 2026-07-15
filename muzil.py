import os
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGWwhTLEDM_nxFzbnmkWMGym3pNd3weS-M" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
DATABASE_URL = "postgresql://postgres.plqrkoszdqnxaghcshik:Fortnite_123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ФУНКЦИИ БД (таблица subscriptions1) ---
async def add_to_db(user_id, artist_name, artist_id=None):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
            user_id, artist_name, str(artist_id) if artist_id else "0"
        )
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound. Кидай ссылку или название трека.")

@dp.message(Command("subscribe"))
async def subscribe(m: types.Message):
    # Очищаем команду
    text = m.text.replace("/subscribe", "").strip()
    if not text:
        await m.answer("Напиши имя артиста: /subscribe [Имя]")
        return
    
    search = yandex_client.search(text, type_='artist')
    if search.artists:
        artist = search.artists.results[0]
        await add_to_db(m.from_user.id, artist.name, artist.id)
        await m.answer(f"✅ Ты подписан на уведомления от {artist.name}!")
    else:
        await m.answer("Артист не найден.")

@dp.message(F.text)
async def handle_all_messages(m: types.Message):
    # Если это команда - игнорируем, она обработается другими функциями
    if m.text.startswith('/'):
        return
        
    msg = await m.answer("🔍 Ищу трек...")
    
    try:
        # Пытаемся найти трек по любому тексту
        search_result = yandex_client.search(m.text, type_='track')
        
        if search_result.tracks and search_result.tracks.results:
            track = search_result.tracks.results[0]
            artist_name = ", ".join([a.name for a in track.artists])
            
            # Сохраняем в базу
            await add_to_db(m.from_user.id, track.title, track.id)
            
            # Отвечаем пользователю
            await msg.edit_text(f"✅ Нашел: {track.title} — {artist_name}\n\n👉 Чтобы скачать, используй /download {track.id}")
        else:
            await msg.edit_text("❌ Ничего не нашел по этому запросу.")
            
    except Exception as e:
        await msg.edit_text(f"Ошибка поиска: {e}")

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="subscribe", description="Подписка"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

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

# --- ФУНКЦИИ БД ---
async def add_to_db(user_id, artist_name, artist_id="0"):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
            user_id, artist_name, str(artist_id)
        )
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound. Кидай название трека или ссылку для поиска.")

@dp.message(Command("subscribe"))
async def subscribe(m: types.Message):
    # Убираем команду из текста, чтобы остался только аргумент
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

@dp.message(Command("history"))
async def show_history(m: types.Message):
    # Код получения истории...
    await m.answer("🕒 История (пока в разработке)")

@dp.message(F.text)
async def handle_search(m: types.Message):
    # ЭТОТ ФИЛЬТР ВАЖЕН:
    # Если сообщение начинается с /, бот вообще не заходит в эту функцию
    if m.text.startswith('/'):
        return
        
    msg = await m.answer("🔍 Ищу...")
    
    try:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks and res.tracks.results:
            track = res.tracks.results[0]
            artist_name = ", ".join([a.name for a in track.artists])
            await add_to_db(m.from_user.id, track.title, track.id)
            await msg.edit_text(f"✅ Нашел: {track.title} — {artist_name}")
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="subscribe", description="Подписка"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

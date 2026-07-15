import os
import asyncio
import requests
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand
from yandex_music import Client
from aiohttp import web

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAGWwhTLEDM_nxFzbnmkWMGym3pNd3weS-M" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
DATABASE_URL = "postgresql://postgres.plqrkoszdqnxaghcshik:Fortnite_123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
async def add_to_history(user_id, title, artist):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("INSERT INTO subscriptions (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
                           user_id, title, artist)
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

async def get_history(user_id):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("SELECT artist_name FROM subscriptions WHERE user_id = $1 ORDER BY id DESC LIMIT 5", user_id)
        await conn.close()
        return rows
    except Exception as e:
        print(f"Ошибка БД: {e}")
        return []

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound. Теперь я записываю в историю только найденную музыку!")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    rows = await get_history(m.from_user.id)
    if not rows: 
        await m.answer("История пуста.")
    else: 
        history_text = "\n".join([f"- {r['artist_name']}" for r in rows])
        await m.answer(f"🕒 Последние найденные треки:\n{history_text}")

@dp.message(F.text)
async def handle_search(m: types.Message):
    # Игнорируем команды, чтобы они не попадали в поиск
    if m.text.startswith('/'):
        return
        
    msg = await m.answer("🔍 Ищу трек...")
    
    try:
        res = yandex_client.search(m.text, type_='track')
        
        if res.tracks and res.tracks.results:
            track = res.tracks.results[0]
            artist_name = ", ".join([a.name for a in track.artists])
            
            # Сохраняем в базу ТОЛЬКО при успешном нахождении трека
            await add_to_history(m.from_user.id, track.title, artist_name)
            
            await msg.edit_text(f"✅ Нашел: {track.title} — {artist_name}\n\nТеперь ты можешь скачать его!")
        else:
            await msg.edit_text("❌ Ничего не нашел по этому запросу.")
            
    except Exception as e:
        await msg.edit_text(f"Ошибка при поиске: {e}")

# --- ЗАПУСК ---
async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

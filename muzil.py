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
# Твой пароль вставлен верно, оставь его как есть
DATABASE_URL = "postgresql://postgres.plqrkoszdqnxaghcshik:Fortnite_123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

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
    await m.answer("Привет! Я Skibidi_sound. Моя память теперь в облаке!")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    rows = await get_history(m.from_user.id)
    if not rows: 
        await m.answer("История пуста.")
    else: 
        history_text = "\n".join([f"- {r['artist_name']}" for r in rows])
        await m.answer(f"🕒 Последние скачивания:\n{history_text}")

@dp.message(F.text)
async def handle_search(m: types.Message):
    res = yandex_client.search(m.text, type_='track')
    if res.tracks:
        track = res.tracks.results[0]
        artist_name = ", ".join([a.name for a in track.artists])
        await add_to_history(m.from_user.id, track.title, artist_name)
        await m.answer(f"✅ Добавлено в историю: {track.title} — {artist_name}")
    else:
        await m.answer("Ничего не нашел.")

# --- ЗАПУСК ---
async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

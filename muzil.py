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
yandex_client = Client(YANDEX_TOKEN)

# --- ФУНКЦИИ БД (работают с таблицей subscriptions1) ---
async def add_to_history(user_id, title, artist):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Обрати внимание: имя таблицы здесь subscriptions1
        await conn.execute("INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
                           user_id, title, artist)
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

async def get_history(user_id):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Имя таблицы subscriptions1
        rows = await conn.fetch("SELECT artist_name FROM subscriptions1 WHERE user_id = $1 ORDER BY id DESC LIMIT 5", user_id)
        await conn.close()
        return rows
    except Exception as e:
        return []

# --- ФОНОВАЯ ЗАДАЧА ---
async def check_new_releases():
    while True:
        try:
            print("Проверка новых релизов...")
        except Exception as e:
            print(f"Ошибка: {e}")
        await asyncio.sleep(86400)

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound (версия с базой subscriptions1).")

@dp.message(Command("subscribe"))
async def subscribe(m: types.Message):
    artist_name = m.text.replace("/subscribe ", "").strip()
    if not artist_name or artist_name == "/subscribe":
        await m.answer("Напиши имя артиста: /subscribe [Имя]")
        return
    
    search = yandex_client.search(artist_name, type_='artist')
    if search.artists:
        artist = search.artists.results[0]
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("INSERT INTO subscriptions1 (user_id, artist_id, artist_name) VALUES ($1, $2, $3)",
                           m.from_user.id, str(artist.id), artist.name)
        await conn.close()
        await m.answer(f"✅ Ты подписан на уведомления от {artist.name}!")
    else:
        await m.answer("Артист не найден.")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    rows = await get_history(m.from_user.id)
    if not rows: await m.answer("История пуста.")
    else: 
        text = "\n".join([f"- {r['artist_name']}" for r in rows])
        await m.answer(f"🕒 Последние:\n{text}")

@dp.message(F.text)
async def handle_search(m: types.Message):
    if m.text.startswith('/'): return
    msg = await m.answer("🔍 Ищу...")
    try:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            track = res.tracks.results[0]
            artist_name = ", ".join([a.name for a in track.artists])
            await add_to_history(m.from_user.id, track.title, artist_name)
            await msg.edit_text(f"✅ Нашел: {track.title} — {artist_name}")
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

async def main():
    asyncio.create_task(check_new_releases())
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="subscribe", description="Подписка"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

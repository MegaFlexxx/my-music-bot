import asyncio
import asyncpg
import re
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

# --- ФУНКЦИИ БД ---
async def add_to_db(user_id, title, track_id="0"):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
            user_id, title, str(track_id)
        )
        await conn.close()
    except Exception as e:
        print(f"Ошибка БД: {e}")

# --- ВСПОМОГАТЕЛЬНЫЕ ---
def extract_track_id(text):
    match = re.search(r'track/(\d+)', text)
    return match.group(1) if match else None

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound. Доступные команды:\n/find [название или ссылка]\n/subscribe [имя артиста]\n/history")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT artist_name FROM subscriptions1 WHERE user_id = $1 ORDER BY id DESC LIMIT 5", m.from_user.id)
    await conn.close()
    if not rows: await m.answer("История пуста.")
    else: await m.answer(f"🕒 Последние:\n" + "\n".join([f"- {r['artist_name']}" for r in rows]))

@dp.message(Command("subscribe"))
async def subscribe(m: types.Message):
    text = m.text.replace("/subscribe", "").strip()
    if not text:
        await m.answer("Напиши имя артиста: /subscribe [Имя]")
        return
    search = yandex_client.search(text, type_='artist')
    if search.artists and search.artists.results:
        artist = search.artists.results[0]
        await add_to_db(m.from_user.id, artist.name, artist.id)
        await m.answer(f"✅ Ты подписан на {artist.name}!")
    else:
        await m.answer("Артист не найден.")

@dp.message(Command("find"))
async def find_track(m: types.Message):
    query = m.text.replace("/find", "").strip()
    if not query:
        await m.answer("Введите название или ссылку: /find [запрос]")
        return
    
    msg = await m.answer("🔍 Ищу...")
    try:
        track_id = extract_track_id(query)
        track = None
        if track_id:
            track = yandex_client.tracks([track_id])[0]
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if track:
            name = f"{track.title} — {', '.join([a.name for a in track.artists])}"
            await add_to_db(m.from_user.id, name, track.id)
            await msg.edit_text(f"✅ Нашел: {name}")
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка поиска: {e}")

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="find", description="Найти"),
        BotCommand(command="subscribe", description="Подписка"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

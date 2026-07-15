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
async def add_to_db(user_id, artist_name, artist_id="0"):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
        user_id, artist_name, str(artist_id)
    )
    await conn.close()

async def get_history_from_db(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        "SELECT artist_name FROM subscriptions1 WHERE user_id = $1 ORDER BY id DESC LIMIT 5", 
        user_id
    )
    await conn.close()
    return rows

# --- ФОНОВАЯ ЗАДАЧА (Мониторинг) ---
async def check_new_releases():
    while True:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            subs = await conn.fetch("SELECT DISTINCT user_id, artist_id, artist_name FROM subscriptions1 WHERE artist_id != '0'")
            await conn.close()
            for sub in subs:
                # Фоновая проверка релизов
                pass
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(3600)

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound.\nИспользуй /find [название] для поиска,\n/subscribe [имя] для подписки,\n/history для истории.")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    rows = await get_history_from_db(m.from_user.id)
    if not rows: await m.answer("История пуста.")
    else: 
        text = "\n".join([f"- {r['artist_name']}" for r in rows])
        await m.answer(f"🕒 Последние записи:\n{text}")

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
        await m.answer("Введите название: /find [название]")
        return
    msg = await m.answer("🔍 Ищу...")
    try:
        res = yandex_client.search(query, type_='track')
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
    asyncio.create_task(check_new_releases())
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="find", description="Найти трек"),
        BotCommand(command="subscribe", description="Подписаться"),
        BotCommand(command="history", description="История")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

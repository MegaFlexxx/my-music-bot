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

# --- ФУНКЦИИ БД ---
async def add_to_db(user_id, artist_name, artist_id="0"):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
        user_id, artist_name, str(artist_id)
    )
    await conn.close()

# --- ФОНОВАЯ ЗАДАЧА (Мониторинг) ---
async def check_new_releases():
    print("Фоновый мониторинг запущен...")
    while True:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            subs = await conn.fetch("SELECT DISTINCT user_id, artist_id, artist_name FROM subscriptions1 WHERE artist_id != '0'")
            await conn.close()

            for sub in subs:
                # Получаем последний трек артиста
                artist_tracks = yandex_client.artists_tracks(sub['artist_id'], page_size=1)
                if artist_tracks.tracks:
                    track = artist_tracks.tracks[0]
                    # Здесь можно добавить проверку: если трек новый (сравнить с БД), шлем уведомление
                    print(f"Проверка: {sub['artist_name']} -> {track.title}")
            
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        
        await asyncio.sleep(3600) # Проверка каждый час

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Я Skibidi_sound. Я слежу за релизами твоих любимых артистов.")

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
        await m.answer(f"✅ Ты подписан на уведомления от {artist.name}!")
    else:
        await m.answer("Артист не найден.")

@dp.message(F.text)
async def handle_search(m: types.Message):
    if m.text.startswith('/'): return
    msg = await m.answer("🔍 Ищу...")
    try:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks and res.tracks.results:
            track = res.tracks.results[0]
            artist_name = ", ".join([a.name for a in track.artists])
            await add_to_db(m.from_user.id, track.title)
            await msg.edit_text(f"✅ Нашел: {track.title} — {artist_name}")
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

async def main():
    # Запуск фоновой задачи
    asyncio.create_task(check_new_releases())
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="subscribe", description="Подписка")
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

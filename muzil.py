import asyncio
import asyncpg
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from yandex_music import Client

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAFUepxkOy7nv_jVqgCD8cl4qceYc_fxoyA" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
DATABASE_URL = "postgresql://postgres.plqrkoszdqnxaghcshik:Fortnite_123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# --- ФУНКЦИЯ БД ---
async def add_to_db(user_id, title, track_id="0"):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("INSERT INTO subscriptions1 (user_id, artist_name, artist_id) VALUES ($1, $2, $3)", 
                           user_id, title, str(track_id))
        await conn.close()
    except Exception: pass

# --- ОБРАБОТЧИК ---
@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    msg = await m.answer("🔍 Ищу...")
    try:
        query = m.text.strip()
        track_id_match = re.search(r'track/(\d+)', query)
        track = None
        if track_id_match:
            track = yandex_client.tracks([track_id_match.group(1)])[0]
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results: track = res.tracks.results[0]
        
        if track:
            track_url = f"https://music.yandex.ru/album/{track.albums[0].id}/track/{track.id}"
            await msg.delete()
            
            # Отправляем ссылку. disable_web_page_preview=False заставляет Telegram показать превью (плашку)
            await m.answer(track_url, disable_web_page_preview=False)
            
            await add_to_db(m.from_user.id, f"{track.title} — {track.artists[0].name}", track.id)
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎧 Слушать / Скачать", url=track_url)]
            ])
            await m.answer("✅ Нашел трек:", reply_markup=kb)
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

# --- КОМАНДЫ (минимальный набор) ---
@dp.message(Command("start"))
async def start(m: types.Message): await m.answer("Привет! Пришли мне название трека.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import asyncpg
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
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

# --- ОБРАБОТЧИК ---
@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    # Убираем лишние сообщения, чтобы не засорять чат
    msg = await m.answer("🔍 Ищу...")
    try:
        query = m.text.strip()
        track_id_match = re.search(r'track/(\d+)', query)
        track = None
        if track_id_match:
            track = yandex_client.tracks([track_id_match.group(1)])[0]
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if track:
            name = f"{track.title} — {', '.join([a.name for a in track.artists])}"
            track_url = f"https://music.yandex.ru/album/{track.albums[0].id}/track/{track.id}"
            
            # Удаляем сообщение "Ищу..."
            await msg.delete()
            
            # 1. Отправляем ссылку, чтобы Telegram нарисовал карточку с обложкой
            await m.answer(track_url)
            
            # 2. Сохраняем в БД
            await add_to_db(m.from_user.id, name, track.id)
            
            # 3. Отправляем кнопку отдельно
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎧 Слушать / Скачать на Яндексе", url=track_url)]
            ])
            await m.answer(f"✅ Нашел: {name}", reply_markup=kb)
        else:
            await msg.edit_text("❌ Ничего не нашел.")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("Привет! Пришли мне ссылку или название, я найду трек.")

@dp.message(Command("history"))
async def show_history(m: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT artist_name FROM subscriptions1 WHERE user_id = $1 ORDER BY id DESC LIMIT 5", m.from_user.id)
    await conn.close()
    await m.answer("🕒 Последние:\n" + "\n".join([f"- {r['artist_name']}" for r in rows]) if rows else "История пуста.")

@dp.message(Command("subscribe"))
async def subscribe(m: types.Message):
    name = m.text.replace("/subscribe", "").strip()
    if not name: return await m.answer("Укажи имя артиста.")
    search = yandex_client.search(name, type_='artist')
    if search.artists and search.artists.results:
        await add_to_db(m.from_user.id, search.artists.results[0].name, search.artists.results[0].id)
        await m.answer(f"✅ Подписан на {search.artists.results[0].name}")

@dp.message(Command("subscriptions"))
async def show_subs(m: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    subs = await conn.fetch("SELECT DISTINCT artist_name FROM subscriptions1 WHERE user_id = $1 AND artist_id != '0'", m.from_user.id)
    await conn.close()
    await m.answer("Твои подписки:\n" + "\n".join([f"• {s['artist_name']}" for s in subs]) if subs else "Нет подписок.")

@dp.message(Command("unsubscribe"))
async def unsubscribe(m: types.Message):
    name = m.text.replace("/unsubscribe", "").strip()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM subscriptions1 WHERE user_id = $1 AND artist_name = $2", m.from_user.id, name)
    await conn.close()
    await m.answer("✅ Готово.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

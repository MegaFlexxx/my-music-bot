import asyncio
import os
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# Твои данные
TELEGRAM_TOKEN = "8632244991:AAGSj6V48pH9xz2S5sAIGVj96N52M2pcgPg"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# Веб-сервер для Render (обязательно для бесплатного тарифа)
async def handle(request):
    return web.Response(text="Bot is running")

@dp.message(Command("start"))
async def start_handler(m: types.Message):
    await m.answer("Привет! Пришли название трека или ссылку, я пришлю его с обложкой.")

@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    status_msg = await m.answer("🔍 Ищу...")
    try:
        query = m.text.strip()
        track = None
        
        # Поиск: если ссылка - берем ID, если текст - ищем поиском
        track_id_match = re.search(r'track/(\d+)', query)
        if track_id_match:
            tracks = yandex_client.tracks([track_id_match.group(1)])
            if tracks: track = tracks[0]
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if not track:
            await status_msg.edit_text("❌ Не найдено.")
            return

        audio_name = f"{track.id}.mp3"
        cover_name = f"{track.id}.jpg"
        
        # Скачивание
        track.download(audio_name)
        if track.cover_uri:
            track.download_cover(cover_name, size='200x200')
            
        # Отправка с обложкой
        await m.answer_audio(
            audio=FSInputFile(audio_name),
            caption=f"✅ {track.title} — {', '.join([a.name for a in track.artists])}",
            title=track.title,
            performer=', '.join([a.name for a in track.artists]),
            thumbnail=FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        
        await status_msg.delete()
        
        # Удаление файлов
        if os.path.exists(audio_name): os.remove(audio_name)
        if os.path.exists(cover_name): os.remove(cover_name)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")

async def main():
    # Запуск веб-сервера
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    
    # Очистка очереди перед стартом
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

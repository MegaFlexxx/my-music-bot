import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

TELEGRAM_TOKEN = "8632244991:AAGSj6V48pH9xz2S5sAIGVj96N52M2pcgPg" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# Веб-сервер для Render (решает ошибку No open ports)
async def handle(request):
    return web.Response(text="Bot is running")

@dp.message(Command("start"))
async def start_handler(m: types.Message):
    await m.answer("Привет! Пришли название трека, я пришлю его с обложкой.")

@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    msg = await m.answer("🔍 Ищу...")
    try:
        query = m.text.strip()
        res = yandex_client.search(query, type_='track')
        if not res.tracks or not res.tracks.results:
            return await msg.edit_text("❌ Не найдено.")
        
        track = res.tracks.results[0]
        audio_name = f"{track.id}.mp3"
        cover_name = f"{track.id}.jpg"
        
        # Скачиваем аудио и обложку
        track.download(audio_name)
        if track.cover_uri:
            track.download_cover(cover_name, size='200x200')
            
        # ОТПРАВКА С ОБЛОЖКОЙ
        await m.answer_audio(
            audio=FSInputFile(audio_name),
            caption=f"✅ {track.title} — {track.artists[0].name}",
            title=track.title,
            performer=track.artists[0].name,
            thumbnail=FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        
        await msg.delete()
        
        # Удаление временных файлов
        if os.path.exists(audio_name): os.remove(audio_name)
        if os.path.exists(cover_name): os.remove(cover_name)
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")

async def main():
    # Запуск веб-сервера
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    
    # Очистка очереди обновлений (убирает дубли)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from yandex_music import Client

# Токены
TELEGRAM_TOKEN = "8632244991:AAE58ZHOF3_TbNNlXhmHjTaSRBim1gBByQo"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN)

# Это «пинг-эндпоинт» для UptimeRobot
async def handle(request):
    return web.Response(text="Bot is running")

@dp.message(Command("start"))
async def start_handler(m: types.Message):
    await m.answer("Привет! Пришли трек (ссылку или название), я пришлю его файлом.")

@dp.message(F.text & ~F.text.startswith('/'))
async def auto_handle(m: types.Message):
    msg = await m.answer("🔍 Ищу...")
    try:
        query = m.text.strip()
        track = None
        # Поиск по ID или названию
        match = re.search(r'track/(\d+)', query)
        if match:
            tracks = yandex_client.tracks([match.group(1)])
            track = tracks[0] if tracks else None
        else:
            res = yandex_client.search(query, type_='track')
            if res.tracks and res.tracks.results:
                track = res.tracks.results[0]
        
        if not track:
            return await msg.edit_text("❌ Ничего не нашел.")

        audio_name = f"{track.id}.mp3"
        cover_name = f"{track.id}.jpg"
        
        track.download(audio_name)
        if track.cover_uri:
            track.download_cover(cover_name, size='200x200')
            
        await m.answer_audio(
            audio=FSInputFile(audio_name),
            caption=f"✅ {track.title}",
            title=track.title,
            performer=', '.join([a.name for a in track.artists]),
            thumbnail=FSInputFile(cover_name) if os.path.exists(cover_name) else None
        )
        await msg.delete()
        
        if os.path.exists(audio_name): os.remove(audio_name)
        if os.path.exists(cover_name): os.remove(cover_name)
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

async def main():
    # Запуск веб-сервера (для Render и UptimeRobot)
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Порт берем из переменной среды
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Очистка очереди обновлений
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

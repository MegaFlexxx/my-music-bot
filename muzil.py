import sys
import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client
from aiohttp import web

# --- ПАТЧ API (должен быть до всего) ---
def apply_patch():
    try:
        import yandex_music
        if hasattr(yandex_music, 'Product'):
            original_init = yandex_music.Product.__init__
            def patched_init(self, *args, **kwargs):
                kwargs.setdefault('common_period_duration', None)
                original_init(self, *args, **kwargs)
            yandex_music.Product.__init__ = patched_init
    except ImportError: pass
apply_patch()

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = "8632244991:AAEBJti86glaGMXh6N6FGY-XcJWywnWVzYg" # СЮДА НОВЫЙ ТОКЕН
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ВЕБ-СЕРВЕР (без потоков) ---
async def web_app_factory():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Бот жив"))
    return app

# --- ЗАПУСК ---
async def main():
    runner = web.AppRunner(await web_app_factory())
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

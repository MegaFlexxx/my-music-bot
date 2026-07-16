import sys
import os
import asyncio
import requests
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from aiohttp import web

# --- ПАТЧ YANDEX MUSIC ---
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
TELEGRAM_TOKEN = "8632244991:AAE58ZHOF3_TbNNlXhmHjTaSRBim1gBByQo" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ЛОГИКА СКАЧИВАНИЯ С КРАСИВЫМ ОФОРМЛЕНИЕМ ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥 Ищу трек...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        # Скачиваем трек
        info = track.get_download_info()
        link = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: 
            f.write(requests.get(link, timeout=15).content)
        
        # Скачиваем обложку (если есть)
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_cover_url = cover_url if cover_url.startswith('http') else "https:" + cover_url
            with open(c_name, 'wb') as f: 
                f.write(requests.get(full_cover_url, timeout=10).content)
            Image.open(c_name).convert('RGB').resize((400, 400)).save(c_name, "JPEG", quality=85)
            
            # Вшиваем обложку в MP3
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: 
                audio.add_tags(ID3=ID3)
            with open(c_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
            audio.save(v2_version=3)
        
        # --- КРАСИВОЕ ОФОРМЛЕНИЕ (БЕЗ Markdown, ЧТОБЫ НЕ БЫЛО ОШИБОК) ---
        # Исполнители
        artists = ", ".join([a.name for a in track.artists])
        
        # Длительность в минутах и секундах
        duration_sec = track.duration_ms // 1000
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Размер файла
        file_size = os.path.getsize(f_name) / (1024 * 1024)  # В МБ
        size_str = f"{file_size:.1f} MB"
        
        # Красивая подпись (БЕЗ Markdown, просто текст)
        caption = (
            f"🎵 {track.title}\n"
            f"👤 Исполнитель: {artists}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"📦 Размер: {size_str}\n\n"
            f"🚽 Бот Skibidi_sound рекомендует!"
        )
        
        # Отправляем аудио с красивым оформлением (БЕЗ parse_mode)
        await message.answer_audio(
            audio=types.FSInputFile(f_name),
            thumbnail=types.FSInputFile(c_name) if os.path.exists(c_name) else None,
            title=track.title,
            performer=artists,
            caption=caption
        )
        
        # Чистим файлы
        for f in [f_name, c_name]: 
            if os.path.exists(f): 
                os.remove(f)
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- ВЕБ-СЕРВЕР ДЛЯ UPTIME ROBOT ---
async def handle(request):
    return web.Response(text="Бот активен")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render сам задает порт через переменную PORT
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер запущен на порту {port}")
    print(f"✅ Пинг-URL: http://0.0.0.0:{port}")

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def start(m: types.Message): 
    await m.answer("🎵 Skibidi_sound — твой музыкальный помощник!\n\nОтправь название трека или исполнителя, и я найду музыку за считанные секунды! 🔥")

@dp.message(F.text)
async def handle_search(m: types.Message):
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
    else:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            track = res.tracks.results[0]
            await m.answer(
                f"✅ Нашел трек!\n\n"
                f"🎵 {track.title} — {track.artists[0].name}\n"
                f"👇 Нажми на кнопку, чтобы скачать",
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[
                        types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")
                    ]]
                )
            )
        else:
            await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

@dp.callback_query(F.data.startswith("down_"))
async def callback_download(c: types.CallbackQuery):
    await c.answer("🔽 Начинаю загрузку...")
    await download_and_send(c.message, c.data.split("_")[1])

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    # Запускаем веб-сервер и бота параллельно
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())

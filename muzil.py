import os

# Отключаем использование системных прокси (VPN) для requests и aiohttp глобально в скрипте.
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

# --- ЗАПЛАТКА ДЛЯ ОБХОДА ОШИБКИ ЯНДЕКСА ---
import yandex_music
if hasattr(yandex_music, 'Product'):
    original_init = yandex_music.Product.__init__
    def patched_init(self, *args, **kwargs):
        kwargs.setdefault('common_period_duration', None)
        original_init(self, *args, **kwargs)
    yandex_music.Product.__init__ = patched_init
# ------------------------------------------

import re
import logging
import asyncio
import aiohttp
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yandex_music import Client

# Импортируем mutagen для вшивания обложки и тегов в MP3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, error

# =================== НАСТРОЙКИ ===================
TELEGRAM_TOKEN = "8971955986:AAE8L7Lab3mxnpGAwRwTyGkMpPatRUiJhs0"
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"
# =================================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализируем клиент Яндекс Музыки
yandex_client = Client(YANDEX_TOKEN).init()

TRACK_RE = re.compile(r"track/(\d+)")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Теперь я умею искать музыку прямо в чате!\n\n"
        "Вы можете:\n"
        "1️⃣ Отправить мне **ссылку на трек** из Яндекс Музыки.\n"
        "2️⃣ Или просто написать **название песни и исполнителя** (например: `Miyagi Кассандра`), и я сам найду её!"
    )

@dp.message(F.text)
async def handle_message(message: types.Message):
    query = message.text.strip()
    match = TRACK_RE.search(query)
    
    # Сначала определяем ID трека: либо вытаскиваем из ссылки, либо ищем по названию
    track_id = None
    
    if match:
        track_id = match.group(1)
        status_msg = await message.answer("🔍 Обрабатываю ссылку на трек...")
    else:
        # Если это не ссылка, то выполняем поиск
        status_msg = await message.answer(f"🔍 Ищу трек по запросу: *{query}*...", parse_mode="Markdown")
        try:
            # Ищем трек на Яндексе (берем первую страницу результатов)
            search_result = yandex_client.search(query, type_='track')
            
            # Проверяем, нашлись ли треки
            if search_result.tracks and search_result.tracks.results:
                best_match = search_result.tracks.results[0]
                track_id = best_match.id
                logging.info(f"Найден трек по поиску: ID {track_id} ({best_match.title})")
            else:
                await status_msg.edit_text("❌ К сожалению, ничего не нашлось по этому названию. Попробуй уточнить имя артиста.")
                return
        except Exception as search_err:
            logging.error(f"Ошибка при поиске: {search_err}")
            await status_msg.edit_text("💥 Произошла ошибка при поиске трека на сервере Яндекса.")
            return

    # Запускаем стандартный процесс скачивания трека по полученному track_id
    try:
        # Получаем информацию о треке
        tracks = yandex_client.tracks([track_id])
        if not tracks:
            await status_msg.edit_text("❌ Трек не найден.")
            return
        
        track = tracks[0]
        title = track.title
        artists = ", ".join([artist.name for artist in track.artists])
        file_name = f"{artists} - {title}.mp3"
        
        # Очищаем имя файла от запрещенных символов
        file_name = "".join(c for c in file_name if c.isalnum() or c in " -_.").strip()
        cover_name = f"cover_{track_id}.jpg"

        await status_msg.edit_text(f"📥 Скачиваю: *{artists} — {title}*...", parse_mode="Markdown")

        # Получаем структуру скачивания
        info = track.get_download_info()
        best_info = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0]
        download_link = best_info.get_direct_link()

        # Скачиваем трек асинхронно
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.get(download_link) as response:
                if response.status == 200:
                    with open(file_name, 'wb') as f:
                        f.write(await response.read())
                else:
                    await status_msg.edit_text("❌ Не удалось скачать файл с серверов Яндекса.")
                    return
            
        # Скачиваем обложку через requests напрямую
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            if cover_url.startswith('//'):
                cover_url = "https:" + cover_url
            elif not cover_url.startswith('http'):
                cover_url = "https://" + cover_url
            
            try:
                cover_response = requests.get(cover_url, timeout=10)
                if cover_response.status_code == 200:
                    with open(cover_name, 'wb') as f:
                        f.write(cover_response.content)
                    logging.info(f"Обложка успешно сохранена: {cover_name}")
                else:
                    logging.error(f"Сервер вернул код {cover_response.status_code} при скачивании обложки")
            except Exception as cover_err:
                logging.error(f"Не удалось скачать обложку через requests: {cover_err}")

        # Вшиваем обложку и метаданные в MP3-файл
        if os.path.exists(file_name):
            try:
                audio = MP3(file_name, ID3=ID3)
                try:
                    audio.add_tags()
                except error:
                    pass

                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=artists))

                if os.path.exists(cover_name) and os.path.getsize(cover_name) > 0:
                    with open(cover_name, 'rb') as img:
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,
                                desc=u'Cover',
                                data=img.read()
                            )
                        )
                    logging.info("Обложка успешно вшита в ID3-теги трека")
                
                audio.save()
            except Exception as meta_err:
                logging.error(f"Не удалось записать теги: {meta_err}")

        # Отправляем файл в Telegram
        if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
            await status_msg.edit_text("📤 Отправляю файл в Telegram...")
            
            audio_file = types.FSInputFile(file_name)
            
            thumb_file = None
            if os.path.exists(cover_name) and os.path.getsize(cover_name) > 0:
                thumb_file = types.FSInputFile(cover_name)

            await message.answer_audio(
                audio=audio_file,
                title=title,
                performer=artists,
                thumbnail=thumb_file
            )
            
            # Удаляем временные файлы
            os.remove(file_name)
            if os.path.exists(cover_name):
                os.remove(cover_name)
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Ошибка: скачанный файл пуст.")

    except Exception as e:
        logging.error(f"Ошибка при обработке трека: {e}", exc_info=True)
        await status_msg.edit_text("💥 Произошла ошибка при обработке трека. Проверьте подключение к сети.")
        if 'file_name' in locals() and os.path.exists(file_name):
            os.remove(file_name)
        if 'cover_name' in locals() and os.path.exists(cover_name):
            os.remove(cover_name)

async def main():
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

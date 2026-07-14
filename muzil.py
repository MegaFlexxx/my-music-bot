import os

# Отключаем использование системных прокси (VPN) для requests и aiohttp глобально в скрипте.
# Это заставит запросы к Яндексу идти напрямую, минуя туннель Hiddify.
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

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

# Инициализируем клиент Яндекс Музыки в стандартном режиме (переменные окружения выше сами отключат прокси)
yandex_client = Client(YANDEX_TOKEN).init()

TRACK_RE = re.compile(r"track/(\d+)")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Отправь мне ссылку на трек из Яндекс Музыки, "
        "и я скачаю его для тебя с оригинальной обложкой и тегами."
    )

@dp.message(F.text)
async def handle_message(message: types.Message):
    url = message.text
    match = TRACK_RE.search(url)
    
    if not match:
        await message.answer("❌ Хм, это не похоже на ссылку на трек Яндекс Музыки. Отправь ссылку вида `https://music.yandex.ru/.../track/123456`")
        return

    track_id = match.group(1)
    status_msg = await message.answer("🔍 Ищу трек и подготавливаю к загрузке...")

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
            
        # Скачиваем обложку через requests напрямую (без прокси)
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            if cover_url.startswith('//'):
                cover_url = "https:" + cover_url
            elif not cover_url.startswith('http'):
                cover_url = "https://" + cover_url
            
            try:
                # Загружаем обложку напрямую
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
                    pass  # Теги уже существуют

                # Записываем Название и Исполнителя в свойства файла
                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=artists))

                # Вшиваем обложку в сам файл (ID3-тег APIC)
                if os.path.exists(cover_name) and os.path.getsize(cover_name) > 0:
                    with open(cover_name, 'rb') as img:
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,  # 3 означает "front cover" (обложка)
                                desc=u'Cover',
                                data=img.read()
                            )
                        )
                    logging.info("Обложка успешно вшита в ID3-теги трека")
                else:
                    logging.warning("Файл обложки отсутствует или пуст, вшивание в теги пропущено")
                
                audio.save()
            except Exception as meta_err:
                logging.error(f"Не удалось записать теги: {meta_err}")

        # Отправляем файл в Telegram
        if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
            await status_msg.edit_text("📤 Отправляю файл в Telegram...")
            
            audio_file = types.FSInputFile(file_name)
            
            # Подготавливаем файл обложки для принудительного превью
            thumb_file = None
            if os.path.exists(cover_name) and os.path.getsize(cover_name) > 0:
                thumb_file = types.FSInputFile(cover_name)

            await message.answer_audio(
                audio=audio_file,
                title=title,
                performer=artists,
                thumbnail=thumb_file  # Принудительно передаем обложку для отображения в чате
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
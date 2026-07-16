import sys
import os
import asyncio
import requests
import json
import pydantic
from PIL import Image
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonWebApp, WebAppInfo
from aiogram.client.session.aiohttp import AiohttpSession
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
TELEGRAM_TOKEN = "8632244991:AAETPh8Qsyae-d-Zos5d_QBdua6wEdFR3IU" 
YANDEX_TOKEN = "y0__wgBEJT5nK4GGN74BiCym9WjGDDFi8SaCKwoXV-dgMoPE14J0dZHJkGMOiQG"

session = AiohttpSession()
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()
yandex_client = Client(YANDEX_TOKEN).init()

# --- ХРАНИЛИЩЕ РЕЗУЛЬТАТОВ ПОИСКА ---
user_search_results = {}
user_current_position = {}

# --- ПОКАЗ ТРЕКА ---
async def show_track(message: types.Message, user_id: int, position: int):
    results = user_search_results.get(user_id, [])
    if not results or position >= len(results):
        await message.answer("❌ Треки закончились!")
        return
    
    track = results[position]
    total = len(results)
    artists = ", ".join([a.name for a in track.artists])
    
    buttons = []
    buttons.append([types.InlineKeyboardButton(text="📥 Скачать трек", callback_data=f"down_{track.id}")])
    
    nav_buttons = []
    if position > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav_{user_id}_{position-1}"))
    if position < total - 1:
        nav_buttons.append(types.InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"nav_{user_id}_{position+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([types.InlineKeyboardButton(text=f"📌 {position+1}/{total}", callback_data="ignore")])
    
    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        f"🎵 **{track.title}**\n"
        f"👤 **Исполнитель:** {artists}\n"
        f"📌 **Результат {position+1} из {total}**\n\n"
        f"👇 Нажми на кнопку, чтобы скачать",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- СКАЧИВАНИЕ ---
async def download_and_send(message: types.Message, track_id: str):
    msg = await message.answer("📥 Ищу трек...")
    try:
        track = yandex_client.tracks([track_id])[0]
        f_name, c_name = f"{track_id}.mp3", f"{track_id}.jpg"
        
        info = track.get_download_info()
        link = sorted(info, key=lambda x: x.bitrate_in_kbps, reverse=True)[0].get_direct_link()
        with open(f_name, 'wb') as f: 
            f.write(requests.get(link, timeout=15).content)
        
        cover_url = track.get_cover_url('400x400')
        if cover_url:
            full_cover_url = cover_url if cover_url.startswith('http') else "https:" + cover_url
            with open(c_name, 'wb') as f: 
                f.write(requests.get(full_cover_url, timeout=10).content)
            Image.open(c_name).convert('RGB').resize((400, 400)).save(c_name, "JPEG", quality=85)
            audio = MP3(f_name, ID3=ID3)
            if audio.tags is None: 
                audio.add_tags(ID3=ID3)
            with open(c_name, 'rb') as img:
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()))
            audio.save(v2_version=3)
        
        artists = ", ".join([a.name for a in track.artists])
        track_title = track.title
        
        duration_sec = track.duration_ms // 1000
        minutes, seconds = duration_sec // 60, duration_sec % 60
        duration_str = f"{minutes}:{seconds:02d}"
        file_size = os.path.getsize(f_name) / (1024 * 1024)
        size_str = f"{file_size:.1f} MB"
        
        caption = (
            f"🔥 {track_title}\n"
            f"🎤 Исполнитель: {artists}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"💿 Размер: {size_str}\n\n"
            f"🎧 Skibidi_sound бахает для тебя!"
        )
        
        await message.answer_audio(
            audio=types.FSInputFile(f_name),
            thumbnail=types.FSInputFile(c_name) if os.path.exists(c_name) else None,
            title=track_title,
            performer=artists,
            caption=caption
        )
        
        for f in [f_name, c_name]:
            if os.path.exists(f): 
                os.remove(f)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- ВЕБ-СЕРВЕР ---
async def handle(request): 
    return web.Response(text="Бот активен")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер на порту {port}")

# --- МЕНЮ КОМАНД ---
async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("✅ Меню команд установлено!")

# --- ОБРАБОТЧИК КОМАНДЫ /START ---
@dp.message(CommandStart())
async def start_command(m: types.Message):
    await m.answer(
        "🎵 **Skibidi_sound** — твой музыкальный помощник!\n\n"
        "🔥 Отправь название трека или исполнителя, и я найду музыку!\n"
        "🎮 Или нажми кнопку **🎵 Плеер** внизу экрана!",
        parse_mode="Markdown"
    )

# --- ОБРАБОТЧИК ПОИСКА (ТЕКСТ) ---
@dp.message(F.text)
async def search_command(m: types.Message):
    if m.text.startswith('/'):
        return
    
    if "/track/" in m.text:
        await download_and_send(m, m.text.split("/track/")[1].split("?")[0])
    else:
        res = yandex_client.search(m.text, type_='track')
        if res.tracks:
            user_id = m.from_user.id
            user_search_results[user_id] = res.tracks.results
            user_current_position[user_id] = 0
            await show_track(m, user_id, 0)
        else:
            await m.answer("❌ Ничего не найдено. Попробуй написать по-другому.")

# --- ОБРАБОТЧИК ДАННЫХ ИЗ ПЛЕЕРА ---
@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    """Обрабатывает данные, отправленные из Mini App"""
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get('action')
        query = data.get('query')
        
        print(f"📩 Получено из плеера: {data}")  # Лог в консоль Render
        
        if action == 'search' and query:
            # Ищем в Яндекс.Музыке
            res = yandex_client.search(query, type_='track')
            if res.tracks:
                track = res.tracks.results[0]
                artists = ", ".join([a.name for a in track.artists])
                
                # Отправляем результат в чат
                await message.answer(
                    f"✅ **Нашёл для тебя!**\n\n"
                    f"🎵 **{track.title}** — {artists}\n"
                    f"👇 Нажми кнопку, чтобы скачать",
                    reply_markup=types.InlineKeyboardMarkup(
                        inline_keyboard=[[
                            types.InlineKeyboardButton(
                                text="📥 Скачать трек",
                                callback_data=f"down_{track.id}"
                            )
                        ]]
                    ),
                    parse_mode="Markdown"
                )
            else:
                await message.answer("❌ Ничего не найдено. Попробуй изменить запрос.")
        
        elif action == 'download':
            track = data.get('track')
            artist = data.get('artist')
            await message.answer(
                f"📥 **Скачиваю:** {track} — {artist}\n\n"
                f"💡 Найди этот трек в боте командой:\n"
                f"`{track} {artist}`",
                parse_mode="Markdown"
            )
        
        elif action == 'like':
            track = data.get('track')
            await message.answer(f"❤️ Ты лайкнул трек: **{track}**!")
        
        elif action == 'add_to_playlist':
            track = data.get('track')
            await message.answer(f"➕ Трек **{track}** добавлен в плейлист!")
            
    except Exception as e:
        print(f"❌ Ошибка обработки web_app_data: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")

# --- CALLBACK ---
@dp.callback_query(F.data.startswith("down_"))
async def download_callback(c: types.CallbackQuery):
    await c.answer("🔄 Скачиваю...")
    track_id = c.data.replace("down_", "")
    await download_and_send(c.message, track_id)

@dp.callback_query(F.data.startswith("nav_"))
async def nav_callback(c: types.CallbackQuery):
    parts = c.data.split("_")
    user_id = int(parts[1])
    position = int(parts[2])
    if c.from_user.id != user_id:
        await c.answer("❌ Это не твой поиск!", show_alert=True)
        return
    user_current_position[c.from_user.id] = position
    await show_track(c.message, user_id, position)
    await c.message.delete()
    await c.answer()

@dp.callback_query(F.data == "ignore")
async def ignore_callback(c: types.CallbackQuery):
    await c.answer()

# --- ГЛАВНАЯ ---
async def main():
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🎵 Плеер",
            web_app=WebAppInfo(url="https://megaflexxx.github.io/my-music-bot/")
        )
    )
    await set_commands()
    await asyncio.gather(start_web_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())

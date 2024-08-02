import os
import tempfile
import telebot
from telebot import types
import re
import threading
import yt_dlp as youtube_dl
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variable setup
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
STICKER_ID = os.getenv('STICKER_ID')
SUDO_USERS = [int(uid) for uid in os.getenv('SUDO_USERS', '').split(',') if uid]

if not TELEGRAM_BOT_TOKEN or not STICKER_ID or not SUDO_USERS:
    logger.error("Missing TELEGRAM_BOT_TOKEN, STICKER_ID, or SUDO_USERS.")
    exit(1)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
url_dict = defaultdict(str)

def sanitize_filename(value):
    return re.sub(r'[\/:*?"<>|]', '_', value)

def download_hook(d):
    if d['status'] == 'downloading':
        logger.info(f"Downloading {d['_percent_str']} ETA: {d['_eta_str']}")

def download_and_send(chat_id, url, option):
    try:
        max_size = 500 * 1024 * 1024
        sticker_message = bot.send_sticker(chat_id, STICKER_ID)
        
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = os.path.join(tempdir, 'output')
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best' if option == 'video' else 'bestaudio',
                'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [download_hook],
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                sanitized_title = sanitize_filename(info['title'][:30])
                ext = 'mp4' if option == 'video' else 'm4a'
                output_file = os.path.join(output_dir, f"{sanitized_title}.{ext}")

                if not os.path.isfile(output_file):
                    output_file = [f for f in os.listdir(output_dir) if f.startswith(sanitized_title)][0]
                    output_file = os.path.join(output_dir, output_file)

                if os.path.getsize(output_file) > max_size:
                    bot.send_message(chat_id, "The file size exceeds the 500 MB limit. Try a different video or audio.")
                    return

                with open(output_file, 'rb') as f:
                    if option == 'video':
                        bot.send_video(chat_id, f, timeout=1000)
                    else:
                        bot.send_audio(chat_id, f, timeout=1000)
                bot.delete_message(chat_id, sticker_message.message_id)
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        bot.send_message(chat_id, f"Sorry! Download failed. Please try another. Error: {str(e)}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id in SUDO_USERS:
        bot.reply_to(message, "Welcome! Send me a link, and I'll download it for you!")

def is_valid_url(url):
    pattern = re.compile(r'^(https?:\/\/)?(www\.)?(youtube\.com\/|youtu\.be\/|facebook\.com\/|instagram\.com\/|twitter\.com\/)', re.IGNORECASE)
    return bool(pattern.match(url))

@bot.message_handler(func=lambda message: True)
def handle_downloadable(message):
    if message.from_user.id in SUDO_USERS and is_valid_url(message.text):
        url_dict[message.chat.id] = message.text
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("Video", callback_data=f"video|{message.chat.id}"),
            types.InlineKeyboardButton("Audio", callback_data=f"audio|{message.chat.id}")
        )
        markup.row(types.InlineKeyboardButton("Cancel", callback_data=f"cancel|{message.chat.id}"))
        bot.send_message(message.chat.id, "Choose an option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    option, chat_id = call.data.split('|', 1)
    url = url_dict.get(int(chat_id))

    if option == 'cancel':
        bot.send_message(int(chat_id), "Download canceled.")
    elif option in ['video', 'audio']:
        threading.Thread(target=download_and_send, args=(int(chat_id), url, option)).start()

if __name__ == "__main__":
    logger.info("Bot started.")
    bot.polling(none_stop=True)

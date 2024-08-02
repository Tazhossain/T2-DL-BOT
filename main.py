import os
import tempfile
import telebot
from telebot import types
import re
import threading
import shutil
import yt_dlp as youtube_dl

# Environment variable setup
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
STICKER_ID = os.environ.get('STICKER_ID')
SUDO_USERS = [int(user_id) for user_id in os.environ.get('SUDO_USERS', '').split(',') if user_id]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Global dictionary to store URLs
url_dict = {}

# Function to remove inline keyboard and delete the message
def remove_inline_keyboard(chat_id, message_id):
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        bot.delete_message(chat_id, message_id)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Error removing inline keyboard: {str(e)}")

# Function to sanitize filenames
def sanitize_filename(value):
    return re.sub(r'[\/:*?"<>|]', '_', value)

# Function to handle downloads and send the file to the user
def download_and_send(chat_id, url, option):
    try:
        max_size = 500 * 1024 * 1024  # 500 MB
        sticker_message = bot.send_sticker(chat_id, STICKER_ID)

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = os.path.join(tempdir, 'output')
            os.makedirs(output_dir)

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if option == 'video' else 'bestaudio[ext=m4a]/best',
                'outtmpl': os.path.join(output_dir, f"%(title)s.%(ext)s"),
                'progress_hooks': [download_hook],
            }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                short_title = sanitize_filename(info['title'][:30])
                output_file = os.path.join(output_dir, f"{short_title}.mp4" if option == 'video' else f"{short_title}.m4a")

                if os.path.getsize(output_file) > max_size:
                    bot.send_message(chat_id, "The file size exceeds the 500 MB limit. Please try a different video or audio.")
                    return

                with open(output_file, 'rb') as f:
                    if option == 'video':
                        bot.send_video(chat_id, f, timeout=1000)
                    else:
                        bot.send_audio(chat_id, f, timeout=1000)

                bot.delete_message(chat_id, sticker_message.message_id)

    except Exception as e:
        print(f"Exception in download_and_send: {str(e)}")
        bot.send_message(chat_id, f"Sorry! Download failed. Please try another. Error: {str(e)}")

# Function to handle download progress updates
def download_hook(d):
    if d['status'] == 'finished':
        print('Download finished, now converting...')
    elif d['status'] == 'downloading':
        print(f"Downloading {d['_percent_str']} ETA: {d['_eta_str']}")

# Command handler to welcome users
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id not in SUDO_USERS:
        return
    bot.reply_to(message, "Welcome! This is a powerful Telegram downloader bot. Send me a link, and I'll download it for you!")

# Function to validate URLs
def is_valid_url(url):
    pattern = re.compile(
        r'^(https?:\/\/)?(www\.)?((youtube\.com\/(watch\?v=|embed\/|v\/|.+\?v=)|youtu\.be\/)|([A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6})', 
        re.IGNORECASE)
    return bool(pattern.match(url))

# Message handler to process download requests
@bot.message_handler(func=lambda message: True)
def handle_downloadable(message):
    if message.from_user.id not in SUDO_USERS:
        return
    if not is_valid_url(message.text):
        bot.reply_to(message, "Please provide a valid URL from a supported platform.")
        return

    url_dict[message.chat.id] = message.text

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Video", callback_data=f"video|{message.chat.id}"),
        types.InlineKeyboardButton("Audio", callback_data=f"audio|{message.chat.id}")
    )
    markup.row(
        types.InlineKeyboardButton("Cancel", callback_data=f"cancel|{message.chat.id}")
    )
    bot.send_message(message.chat.id, "Choose an option:", reply_markup=markup)

# Callback query handler to manage download options
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    option, chat_id = call.data.split('|', 1)
    url = url_dict.get(int(chat_id))

    if option == 'cancel':
        bot.send_message(int(chat_id), "Download canceled.")
    elif option in ['video', 'audio']:
        remove_inline_keyboard(int(chat_id), call.message.message_id)
        threading.Thread(target=download_and_send, args=(int(chat_id), url, option)).start()

if __name__ == "__main__":
    try:
        print("Bot started.")
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Error: {str(e)}")

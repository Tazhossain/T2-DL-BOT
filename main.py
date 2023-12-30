import os
import tempfile
import yt_dlp as youtube_dl
import telebot
from telebot import types
import re
import time
import uuid
from flask import Flask, request
import threading
from threading import Thread

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
STICKER_ID = os.environ.get('STICKER_ID')
SUDO_USERS = [int(user_id) for user_id in os.environ.get('SUDO_USERS', '').split(',') if user_id]

#TELEGRAM_BOT_TOKEN, STICKER_ID, SUDO_USERS add these vars on your environment

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

server = Flask(__name__)

@server.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://example.onrender.com/' + TELEGRAM_BOT_TOKEN)   #enter host url
    return "T2 Is Running! Made by Taz", 200

def keep_alive():
    t = Thread(target=run)
    t.start()
    
url_dict = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id not in SUDO_USERS:
        return  # Do not respond to unauthorized users
    bot.reply_to(message, f"Welcome! This is a powerful Telegram downloader bot developed by Taz. Send me a link and I'll download it for you!")

def is_valid_url(url):
    # Regular expression for a broad range of URLs
    pattern = re.compile(
        r'^(?:http|https)://'  # http or https
        r'(?:www\.)?'  # optional www subdomain
        r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'  # domain
        r'[A-Z]{2,6}'  # TLD
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return bool(pattern.match(url))

@bot.message_handler(func=lambda message: True)
def handle_downloadable(message):
    if message.from_user.id not in SUDO_USERS:
        return  # Do not process messages from unauthorized users
    if not is_valid_url(message.text):
        bot.reply_to(message, "Please provide a valid URL from a supported platform.")
        return

    global url_dict
    unique_id = str(uuid.uuid4())[:8]
    url_dict[unique_id] = message.text

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("Video", callback_data=f"video|{unique_id}"),
        types.InlineKeyboardButton("Audio", callback_data=f"audio|{unique_id}")
    )
    markup.row(
        types.InlineKeyboardButton("Cancel", callback_data=f"cancel|{unique_id}")
    )
    bot.send_message(message.chat.id, "Choose an option:", reply_markup=markup)

def download_and_send(chat_id, url, option, quality, message_id):
    try:
        max_size = 1024 * 1024 * 1024
        sticker_message = bot.send_sticker(chat_id, STICKER_ID)

        with tempfile.TemporaryDirectory() as tempdir:
            if option == 'video':
                ydl_opts = {
                    'format': f'bestvideo[height<={quality}]+bestaudio/best',
                    'outtmpl': os.path.join(tempdir, 'video.%(ext)s'),  # Use a fixed file name
                    'merge_output_format': 'mp4',
                    'restrictfilenames': True,
                }
            elif option == 'audio':
                ydl_opts = {
                    'format': f'bestaudio[abr<={quality}][filesize<=' + str(max_size) + ']/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}],
                    'outtmpl': os.path.join(tempdir, 'audio.%(ext)s'),  # Use a fixed file name
                    'merge_output_format': 'mp3',
                    'restrictfilenames': True,
                    'format': 'bestaudio/best',
                }

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                if info.get('filesize') and info['filesize'] > max_size:
                    bot.send_message(chat_id, "The file size exceeds the 50 MB limit. Please try a different video or audio.")
                    return

                if option.startswith('audio'):
                    file_path = os.path.splitext(file_path)[0] + '.mp3'

            try:
                with open(file_path, 'rb') as f:
                    if option.startswith('video'):
                        bot.send_video(chat_id, f, supports_streaming=True, timeout=1000)
                    elif option.startswith('audio'):
                        bot.send_audio(chat_id, f, timeout=1000)
            except Exception as e:
                bot.send_message(chat_id, f"Error sending the downloaded file: {str(e)}")
                bot.delete_message(chat_id, message_id)  # Deleting the quality selection message
                return

            bot.send_chat_action(chat_id, 'upload_document')  
            time.sleep(10)
            bot.delete_message(chat_id, message_id)  # Deleting the quality selection message
            bot.delete_message(chat_id, sticker_message.message_id)

    except Exception as e:
        bot.send_message(chat_id, f"Sorry! download failed. Please try another")
        bot.delete_message(chat_id, message_id)  # Deleting the quality selection message
        bot.delete_message(chat_id, sticker_message.message_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    option, unique_id = call.data.split('|', 1)
    url = url_dict.get(unique_id)
    chat_id = call.message.chat.id
    message_id = call.message.message_id  # Storing the message ID

    if option == 'cancel':
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "Download process canceled.")
        return

    if option == 'video' or option == 'audio':
        markup = types.InlineKeyboardMarkup()
        if option == 'video':
            markup.row(
                types.InlineKeyboardButton("High (720p)", callback_data=f"video_720|{unique_id}"),
                types.InlineKeyboardButton("Medium (480p)", callback_data=f"video_480|{unique_id}")
            )
            markup.row(
                types.InlineKeyboardButton("Low (360p)", callback_data=f"video_360|{unique_id}")
            )
            bot.edit_message_text("Choose a video quality:", chat_id, call.message.message_id, reply_markup=markup)
        elif option == 'audio':
            markup.row(
                types.InlineKeyboardButton("High (192kbps)", callback_data=f"audio_192|{unique_id}"),
                types.InlineKeyboardButton("Medium (128kbps)", callback_data=f"audio_128|{unique_id}")
            )
            markup.row(
                types.InlineKeyboardButton("Low (64kbps)", callback_data=f"audio_64|{unique_id}")
            )
            bot.edit_message_text("Choose an audio quality:", chat_id, call.message.message_id, reply_markup=markup)
        markup.row(
            types.InlineKeyboardButton("Cancel", callback_data=f"cancel|{unique_id}")
        )
        return

    if option.startswith('video') or option.startswith('audio'):
        quality = option.split('_')[1]
        threading.Thread(target=download_and_send, args=(chat_id, url, option.split('_')[0], quality, message_id)).start()

if __name__ == "__main__":
    try:
        print("Bot started.")
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 8080)))
    except Exception as e:
        print(f"Error: {str(e)}")

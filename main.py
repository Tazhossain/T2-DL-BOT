import os
import tempfile
import yt_dlp as youtube_dl
import telebot
from telebot import types
import re
import time
import uuid
import sys
from flask import Flask, request
import requests
from bs4 import BeautifulSoup


TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
STICKER_ID = os.environ.get('STICKER_ID')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

server = Flask(__name__)

@server.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://example.your host.com/' + TELEGRAM_BOT_TOKEN)
    
    redeployed = os.environ.get("REDEPLOYED", "0")
    
    if redeployed == "1":
        # Send "Bot started" message to all sudo users
        for user_id in SUDO_USERS:
            bot_started(user_id)
        
        # Send "Bot started" message to all sudo groups
        for group_id in SUDO_GROUP:
            bot_started(group_id)
        
        # Reset the REDEPLOYED environment variable to avoid sending the message again
        os.environ["REDEPLOYED"] = "0"

    return "!", 200

url_dict = {}

# Add sudo users and sudo group
SUDO_USERS = [1234, 1234]
SUDO_GROUP = -1234, -1234

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id not in SUDO_USERS and message.chat.id not in SUDO_GROUP:
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
    if message.from_user.id not in SUDO_USERS and message.chat.id not in SUDO_GROUP:
        return  # Do not process messages from unauthorized users
    if not is_valid_url(message.text):
        bot.reply_to(message, "Please provide a valid URL from a supported platform.")
        return

    global url_dict
    unique_id = str(uuid.uuid4())[:8]
    url_dict[unique_id] = message.text

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🎞️ Video", callback_data=f"video|{unique_id}"),
        types.InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{unique_id}")
    )
    markup.row(
        types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{unique_id}")
    )
    bot.send_message(message.chat.id, "Choose an option:", reply_markup=markup)
        
def download_video(url, max_size):
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'max_filesize': max_size
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        ydl.download([url])
        file_path = ydl.prepare_filename(info)

    return file_path

def download_audio(url, max_size):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'max_filesize': max_size
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        ydl.download([url])
        file_path = ydl.prepare_filename(info)

    return file_path


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    option, unique_id = call.data.split('|', 1)
    url = url_dict.get(unique_id)
    chat_id = call.message.chat.id
    max_size = 50 * 1024 * 1024

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
            types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel|{unique_id}")
        )
        return

    if option.startswith('video'):
        quality = option.split('_')[1]
        ydl_opts = {
            'format': f'bestvideo[height<={quality}][ext=mp4][filesize<='+str(max_size)+']+bestaudio[ext=m4a]/mp4',
            'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'restrictfilenames': True,
        }
    elif option.startswith('audio'):
        quality = option.split('_')[1]
        ydl_opts = {
            'format': f'bestaudio[abr<={quality}][filesize<=' + str(max_size) + ']/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality}],
            'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
            'merge_output_format': 'mp3',
            'restrictfilenames': True,
            'format': 'bestaudio/best',
        }

    sticker_message = bot.send_sticker(chat_id, STICKER_ID)
    sent_message = None
    with tempfile.TemporaryDirectory() as tempdir:
        ydl_opts['outtmpl'] = os.path.join(tempdir, '%(title)s.%(ext)s')

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if info.get('filesize') and info['filesize'] > max_size:
                bot.send_message(chat_id, "The file size exceeds the 50 MB limit. Please try a different video or audio.")
                return

            if option.startswith('audio'):
                file_path = os.path.splitext(file_path)[0] + '.mp3'

        if option.startswith('video'):
            try:
                with open(file_path, 'rb') as f:
                    sent_message = bot.send_video(chat_id, f, supports_streaming=True, timeout=300)
            except Exception as e:
                bot.send_message(chat_id, f"Error: {str(e)}")

        elif option.startswith('audio'):
            try:
                with open(file_path, 'rb') as f:
                    sent_message = bot.send_audio(chat_id, f, timeout=300)
            except Exception as e:
                bot.send_message(chat_id, f"Error: {str(e)}")

    if sent_message:
        bot.send_chat_action(chat_id, 'upload_document')  # Simulate that the bot is still working
        time.sleep(10) 
        bot.delete_message(chat_id, sticker_message.message_id)
        bot.delete_message(chat_id, call.message.message_id)

def search_youtube(query, max_results=5):
    ydl_opts = {
        'default_search': 'ytsearch',
        'quiet': True,
        'format': 'best'
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)

    return info['entries'][:max_results]

@bot.inline_handler(lambda query: query.query)
def query_text(inline_query):
    search_results = search_youtube(inline_query.query)

    results = []
    for entry in search_results:
        result = types.InlineQueryResultArticle(
            id=entry['id'],
            title=entry['title'],
            description=entry['uploader'],
            input_message_content=types.InputTextMessageContent(message_text=entry['webpage_url']),
            thumb_url=entry['thumbnail']
        )
        results.append(result)

    bot.answer_inline_query(inline_query.id, results)

if __name__ == "__main__":
    try:
        print("Bot started.")
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    except Exception as e:
        print(f"Error: {str(e)}")

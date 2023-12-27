import os
import tempfile
import youtube_dl
from flask import Flask, request
import telebot
from telebot import types

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
SUDO_USERS = [6896853746, 5641016852, 5705686446, 6166566680, 5303266118]  # Add your sudo users

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
server = Flask(__name__)

@server.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id not in SUDO_USERS:
        return
    bot.reply_to(message, "Welcome! This bot can download videos and audios. Just send me a link!")

@bot.message_handler(func=lambda message: True)
def handle_downloadable(message):
    if message.from_user.id not in SUDO_USERS:
        return

    if not message.text or not message.text.startswith(('http://', 'https://')):
        bot.reply_to(message, "Please provide a valid URL.")
        return

    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🎞️ Video", callback_data=f"video|{message.text}"),
               types.InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{message.text}"))
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    bot.send_message(message.chat.id, "Choose an option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    option, url = call.data.split('|', 1)
    chat_id = call.message.chat.id

    if option == 'cancel':
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, "Download process canceled.")
        return

    quality_options = {
        'video': ['720', '480', '360'],
        'audio': ['192', '128', '64']
    }

    markup = types.InlineKeyboardMarkup()
    for quality in quality_options.get(option, []):
        markup.row(types.InlineKeyboardButton(f"{quality} kbps", callback_data=f"{option}_{quality}|{url}"))

    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    bot.edit_message_text(f"Choose {option} quality:", chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('video_', 'audio_')))
def handle_quality_selection(call):
    option, quality_url = call.data.split('|', 1)
    option, quality = option.split('_')
    chat_id = call.message.chat.id

    max_size = 50 * 1024 * 1024
    ydl_opts = {
        'format': f'best{option}[abr<={quality}][filesize<={max_size}]/best',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4' if option == 'video' else 'mp3',
        'restrictfilenames': True,
    }

    with tempfile.TemporaryDirectory() as tempdir:
        ydl_opts['outtmpl'] = os.path.join(tempdir, '%(title)s.%(ext)s')

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(quality_url, download=True)
            except youtube_dl.utils.DownloadError as e:
                bot.send_message(chat_id, f"Error: {e}")
                return

            if info.get('filesize') and info['filesize'] > max_size:
                bot.send_message(chat_id, f"The file size exceeds the 50 MB limit.")
                return

            file_path = ydl.prepare_filename(info)

    with open(file_path, 'rb') as f:
        if option == 'video':
            bot.send_video(chat_id, f, supports_streaming=True)
        elif option == 'audio':
            bot.send_audio(chat_id, f)

    bot.send_message(chat_id, "Download complete!")
    bot.delete_message(chat_id, call.message.message_id)

if __name__ == "__main__":
    try:
        print("Bot started.")
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    except Exception as e:
        print(f"Error: {str(e)}")

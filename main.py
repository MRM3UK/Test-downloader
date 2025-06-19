from urllib.parse import urlparse
import datetime
import telebot
import yt_dlp
import re
import os
import time
from telebot.util import quick_markup
import config

bot = telebot.TeleBot(config.token)
last_edited = {}

# Make sure downloads folder exists
os.makedirs(config.output_folder, exist_ok=True)


def youtube_url_validation(url):
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url)


@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.reply_to(
        message,
        "*Send me a video link* and I'll download it for you. Supports *YouTube*, *Twitter*, *TikTok*, *Reddit*, etc.\n\n_Powered by_ [yt-dlp](https://github.com/yt-dlp/yt-dlp)",
        parse_mode="MARKDOWN",
        disable_web_page_preview=True
    )


def download_video(message, url, audio=False, format_id="mp4"):
    if not urlparse(url).scheme:
        bot.reply_to(message, '❌ Invalid URL')
        return

    if 'youtube' in url and not youtube_url_validation(url):
        bot.reply_to(message, '❌ Invalid YouTube URL')
        return

    msg = bot.reply_to(message, "📥 Downloading...")
    file_prefix = str(int(time.time() * 1000))

    def progress_hook(d):
        if d['status'] == 'downloading':
            try:
                key = f"{message.chat.id}-{msg.message_id}"
                if key not in last_edited or (datetime.datetime.now() - last_edited[key]).total_seconds() > 5:
                    percent = int(d['downloaded_bytes'] * 100 / d['total_bytes'])
                    bot.edit_message_text(
                        f"📥 Downloading `{d['info_dict'].get('title', '...')}`\n\n{percent}%",
                        chat_id=message.chat.id,
                        message_id=msg.message_id,
                        parse_mode="MARKDOWN"
                    )
                    last_edited[key] = datetime.datetime.now()
            except Exception as e:
                print("Progress hook error:", e)

    ydl_opts = {
        'format': format_id,
        'outtmpl': f"{config.output_folder}/{file_prefix}.%(ext)s",
        'progress_hooks': [progress_hook],
        'noplaylist': True,
        'max_filesize': config.max_filesize,
        'cookiefile': 'cookies.txt',
        'quiet': True
    }

    if audio:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3'
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            download = info.get('requested_downloads', [info])[0]
            filepath = download.get('filepath')

        if not filepath or not os.path.exists(filepath):
            bot.edit_message_text("❌ File not found.", message.chat.id, msg.message_id)
            return

        bot.edit_message_text("📤 Sending file...", message.chat.id, msg.message_id)

        if audio:
            bot.send_audio(message.chat.id, open(filepath, 'rb'), reply_to_message_id=message.message_id)
        else:
            try:
                bot.send_video(
                    message.chat.id,
                    open(filepath, 'rb'),
                    reply_to_message_id=message.message_id,
                    width=download.get('width'),
                    height=download.get('height')
                )
            except:
                bot.send_document(message.chat.id, open(filepath, 'rb'), reply_to_message_id=message.message_id)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        print("Download error:", e)
        bot.edit_message_text(f"❌ Error: {str(e)}", message.chat.id, msg.message_id)

    finally:
        for file in os.listdir(config.output_folder):
            if file.startswith(file_prefix):
                os.remove(f"{config.output_folder}/{file}")


@bot.message_handler(commands=['download'])
def command_download(message):
    url = extract_url(message)
    if not url:
        bot.reply_to(message, "Usage: `/download <url>`", parse_mode="MARKDOWN")
        return
    download_video(message, url)


@bot.message_handler(commands=['audio'])
def command_audio(message):
    url = extract_url(message)
    if not url:
        bot.reply_to(message, "Usage: `/audio <url>`", parse_mode="MARKDOWN")
        return
    download_video(message, url, audio=True)


@bot.message_handler(commands=['custom'])
def command_custom(message):
    url = extract_url(message)
    if not url:
        bot.reply_to(message, "Usage: `/custom <url>`", parse_mode="MARKDOWN")
        return
    msg = bot.reply_to(message, "🔍 Getting formats...")
    with yt_dlp.YoutubeDL() as ydl:
        info = ydl.extract_info(url, download=False)

    formats = {
        f"{f.get('resolution', 'n/a')}.{f['ext']}": {'callback_data': f['format_id']}
        for f in info['formats'] if f['video_ext'] != 'none'
    }

    markup = quick_markup(formats, row_width=2)
    bot.delete_message(msg.chat.id, msg.message_id)
    bot.reply_to(message, "Choose a format", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.from_user.id == call.message.reply_to_message.from_user.id:
        url = extract_url(call.message.reply_to_message)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        download_video(call.message.reply_to_message, url, format_id=f"{call.data}+bestaudio")
    else:
        bot.answer_callback_query(call.id, "This is not your request.")


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    if message.chat.type == "private":
        download_video(message, message.text)


def extract_url(message):
    if len(message.text.split()) >= 2:
        return message.text.split()[1]
    elif message.reply_to_message and message.reply_to_message.text:
        return message.reply_to_message.text.strip()
    return None


bot.infinity_polling()

from urllib.parse import urlparse
import datetime
import telebot
import config
import yt_dlp
import re
import os
from telebot.util import quick_markup
import time

bot = telebot.TeleBot(config.token)
last_edited = {}

def youtube_url_validation(url):
    regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/.+'
    return re.match(regex, url)

@bot.message_handler(commands=['start', 'help'])
def start_help(message):
    bot.reply_to(
        message,
        "*Send me a video link* and I'll download it for you!\n\nSupports: *YouTube*, *Instagram*, *Facebook*, *Twitter*, *TikTok*, *Reddit*, and more!\n\n_Powered by_ [yt-dlp](https://github.com/yt-dlp/yt-dlp)",
        parse_mode="MARKDOWN",
        disable_web_page_preview=True
    )

def download_video(message, url, audio=False, format_id="best"):
    if not urlparse(url).scheme or not youtube_url_validation(url):
        bot.reply_to(message, '❌ Invalid URL')
        return

    msg = bot.reply_to(message, '⏬ Downloading...')

    video_title = round(time.time() * 1000)
    filename_template = f'{config.output_folder}/{video_title}.%(ext)s'

    def progress_hook(d):
        if d['status'] == 'downloading':
            try:
                update = False
                key = f"{message.chat.id}-{msg.message_id}"
                now = datetime.datetime.now()
                if last_edited.get(key):
                    if (now - last_edited[key]).total_seconds() > 5:
                        update = True
                else:
                    update = True
                if update:
                    perc = round(d['downloaded_bytes'] * 100 / d['total_bytes'])
                    bot.edit_message_text(
                        f"Downloading **{d['info_dict']['title']}**\nProgress: `{perc}%`",
                        chat_id=message.chat.id,
                        message_id=msg.message_id,
                        parse_mode="Markdown"
                    )
                    last_edited[key] = now
            except: pass

    opts = {
        'format': format_id,
        'outtmpl': filename_template,
        'progress_hooks': [progress_hook],
        'max_filesize': config.max_filesize,
        'quiet': True
    }

    if audio:
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        bot.edit_message_text("📤 Uploading to Telegram...", message.chat.id, msg.message_id)

        filepath = info['requested_downloads'][0]['filepath']
        caption = info.get("title", "Video")
        if audio:
            bot.send_audio(message.chat.id, open(filepath, 'rb'), reply_to_message_id=message.message_id)
        else:
            width = info['requested_downloads'][0].get('width')
            height = info['requested_downloads'][0].get('height')
            try:
                bot.send_video(message.chat.id, open(filepath, 'rb'), width=width, height=height, reply_to_message_id=message.message_id)
            except:
                bot.send_document(message.chat.id, open(filepath, 'rb'), caption=caption, reply_to_message_id=message.message_id)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Failed: {str(e)}", message.chat.id, msg.message_id)

    finally:
        for file in os.listdir(config.output_folder):
            if file.startswith(str(video_title)):
                os.remove(f'{config.output_folder}/{file}')

def log(message, url, media_type):
    if config.logs:
        info = f"Group: {message.chat.title} ({message.chat.id})" if message.chat.type != 'private' else "Private chat"
        bot.send_message(config.logs, f"Request ({media_type}) by @{message.from_user.username}:\n{url}\n{info}")

def get_text(message):
    if len(message.text.split(' ')) > 1:
        return message.text.split(' ')[1]
    elif message.reply_to_message and message.reply_to_message.text:
        return message.reply_to_message.text
    return None

@bot.message_handler(commands=['download'])
def cmd_download(message):
    url = get_text(message)
    if not url:
        return bot.reply_to(message, "⚠️ Use: `/download <url>`", parse_mode="Markdown")
    log(message, url, "video")
    download_video(message, url)

@bot.message_handler(commands=['audio'])
def cmd_audio(message):
    url = get_text(message)
    if not url:
        return bot.reply_to(message, "⚠️ Use: `/audio <url>`", parse_mode="Markdown")
    log(message, url, "audio")
    download_video(message, url, audio=True)

@bot.message_handler(commands=['custom'])
def cmd_custom(message):
    url = get_text(message)
    if not url:
        return bot.reply_to(message, "⚠️ Use: `/custom <url>`", parse_mode="Markdown")

    msg = bot.reply_to(message, '🔎 Fetching formats...')
    try:
        with yt_dlp.YoutubeDL() as ydl:
            info = ydl.extract_info(url, download=False)

        formats = {
            f"{x['resolution']}.{x['ext']}": {"callback_data": f"{x['format_id']}+bestaudio"}
            for x in info['formats'] if x.get('video_ext') != 'none'
        }

        markup = quick_markup(formats, row_width=2)
        bot.delete_message(msg.chat.id, msg.message_id)
        bot.reply_to(message, "Choose a quality:", reply_markup=markup)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", msg.chat.id, msg.message_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_format_selection(call):
    if call.from_user.id == call.message.reply_to_message.from_user.id:
        url = get_text(call.message.reply_to_message)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        download_video(call.message.reply_to_message, url, format_id=call.data)
    else:
        bot.answer_callback_query(call.id, "❌ You didn’t send the request!")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_direct_links(message):
    if message.chat.type == "private":
        log(message, message.text, "video")
        download_video(message, message.text)

bot.infinity_polling()

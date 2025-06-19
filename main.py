from urllib.parse import urlparse import datetime import telebot import config import yt_dlp import re import os from telebot import types from telebot.util import quick_markup import time

bot = telebot.TeleBot(config.token) last_edited = {}

def youtube_url_validation(url): youtube_regex = ( r'(https?://)?(www.)?' r'(youtube|youtu|youtube-nocookie).(com|be)/' r'(watch?v=|embed/|v/|.+?v=)?([^&=%?]{11})')

return re.match(youtube_regex, url)

@bot.message_handler(commands=['start', 'help']) def welcome(message): bot.reply_to( message, "Send me a video link and I'll download it for you. Works with YouTube, Twitter, TikTok, Reddit and more.\n\n_Powered by_ yt-dlp", parse_mode="MARKDOWN", disable_web_page_preview=True)

def download_video(message, url, audio=False, format_id="mp4"): url_info = urlparse(url) if url_info.scheme: if url_info.netloc in ['www.youtube.com', 'youtu.be', 'youtube.com', 'youtu.be']: if not youtube_url_validation(url): bot.reply_to(message, 'Invalid URL') return

def progress(d):
        if d['status'] == 'downloading':
            try:
                update = False
                key = f"{message.chat.id}-{msg.message_id}"
                if last_edited.get(key):
                    if (datetime.datetime.now() - last_edited[key]).total_seconds() >= 5:
                        update = True
                else:
                    update = True

                if update:
                    perc = round(d['downloaded_bytes'] * 100 / d['total_bytes'])
                    bot.edit_message_text(
                        chat_id=message.chat.id, message_id=msg.message_id,
                        text=f"Downloading {d['info_dict'].get('title', 'video')}\n\n{perc}%")
                    last_edited[key] = datetime.datetime.now()
            except Exception as e:
                print(e)

    msg = bot.reply_to(message, 'Downloading...')
    video_title = round(time.time() * 1000)

    ydl_opts = {
        'format': format_id,
        'outtmpl': f'{config.output_folder}/{video_title}.%(ext)s',
        'progress_hooks': [progress],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }] if audio else [],
        'max_filesize': config.max_filesize
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        bot.edit_message_text(
            f"❌ Failed to download.\nError: {str(e)}",
            message.chat.id,
            msg.message_id
        )
        return

    try:
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id, text='Sending file to Telegram...')
        filepath = info['requested_downloads'][0]['filepath']
        if audio:
            bot.send_audio(message.chat.id, open(filepath, 'rb'), reply_to_message_id=message.message_id)
        else:
            width = info['requested_downloads'][0].get('width', None)
            height = info['requested_downloads'][0].get('height', None)
            try:
                bot.send_video(
                    message.chat.id,
                    open(filepath, 'rb'),
                    reply_to_message_id=message.message_id,
                    width=width,
                    height=height
                )
            except Exception as e:
                print("send_video failed, fallback to document", e)
                bot.send_document(
                    message.chat.id,
                    open(filepath, 'rb'),
                    reply_to_message_id=message.message_id,
                    caption="Video sent as document (fallback due to size or format)."
                )
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        print("Sending failed:", e)
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=f"❌ Failed to send file.\nError: {e}",
            parse_mode="MARKDOWN")

    for file in os.listdir(config.output_folder):
        if file.startswith(str(video_title)):
            os.remove(f'{config.output_folder}/{file}')
else:
    bot.reply_to(message, 'Invalid URL')

def log(message, text: str, media: str): if config.logs: chat_info = "Private chat" if message.chat.type == 'private' else f"Group: {message.chat.title} ({message.chat.id})" bot.send_message( config.logs, f"Download request ({media}) from @{message.from_user.username} ({message.from_user.id})\n\n{chat_info}\n\n{text}")

def get_text(message): if len(message.text.split(' ')) < 2: return message.reply_to_message.text if message.reply_to_message and message.reply_to_message.text else None else: return message.text.split(' ')[1]

@bot.message_handler(commands=['download']) def download_command(message): text = get_text(message) if not text: bot.reply_to(message, 'Invalid usage, use /download url', parse_mode="MARKDOWN") return log(message, text, 'video') download_video(message, text)

@bot.message_handler(commands=['audio']) def download_audio_command(message): text = get_text(message) if not text: bot.reply_to(message, 'Invalid usage, use /audio url', parse_mode="MARKDOWN") return log(message, text, 'audio') download_video(message, text, True)

@bot.message_handler(commands=['custom']) def custom(message): text = get_text(message) if not text: bot.reply_to(message, 'Invalid usage, use /custom url', parse_mode="MARKDOWN") return msg = bot.reply_to(message, 'Getting formats...') with yt_dlp.YoutubeDL() as ydl: info = ydl.extract_info(text, download=False) data = {f"{x['resolution']}.{x['ext']}": {'callback_data': f"{x['format_id']}"} for x in info['formats'] if x['video_ext'] != 'none'} markup = quick_markup(data, row_width=2) bot.delete_message(msg.chat.id, msg.message_id) bot.reply_to(message, "Choose a format", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True) def callback(call): if call.from_user.id == call.message.reply_to_message.from_user.id: url = get_text(call.message.reply_to_message) bot.delete_message(call.message.chat.id, call.message.message_id) download_video(call.message.reply_to_message, url, format_id=f"{call.data}+bestaudio") else: bot.answer_callback_query(call.id, "You didn't send the request")

@bot.message_handler(func=lambda m: True, content_types=["text", "pinned_message", "photo", "audio", "video", "location", "contact", "voice", "document"]) def handle_private_messages(message): text = message.text or message.caption or None if message.chat.type == 'private': log(message, text, 'video') download_video(message, text)

bot.infinity_polling()

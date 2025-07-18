import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import subprocess
import threading
import pymongo
import feedparser
from config import *
from bs4 import BeautifulSoup
import yt_dlp
import os

# Safe webhook import with error handling
try:
    from webhook import start_webhook
except ImportError as e:
    print(f"Webhook import error: {e}")
    def start_webhook():
        print("Webhook disabled due to import error")

# Import RSS module with error handling
try:
    from modules.rss.rss import news_feed_loop, format_rss_entry, extract_youtube_watch_url
except ImportError as e:
    print(f"RSS module import error: {e}")
    # Create dummy functions if import fails
    async def news_feed_loop(*args):
        print("RSS module disabled")
    
    async def format_rss_entry(entry):
        title = entry.title if 'title' in entry else 'No Title'
        summary = entry.summary if 'summary' in entry else ''
        link = entry.link if 'link' in entry else ''
        thumbnail_url = entry.media_thumbnail[0]['url'] if 'media_thumbnail' in entry else None
        
        msg = (
            f"<b><blockquote>{title}</blockquote></b>\n"
            f"<b><blockquote expandable><i>{summary}</i></blockquote></b>\n"
            f"<b><blockquote><a href='{link}'>Read Full News</a></blockquote></b>"
        )
        return msg, thumbnail_url, link
    
    def extract_youtube_watch_url(yt_url):
        if "youtube.com/embed/" in yt_url:
            video_id = yt_url.split("youtube.com/embed/")[-1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        elif "youtube.com/watch" in yt_url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(yt_url)
            v = parse_qs(parsed.query).get("v", [""])[0]
            if v:
                return f"https://www.youtube.com/watch?v={v}"
        return yt_url

# MongoDB connection with error handling
try:
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db = mongo_client["AnimeNewsBot"]
    user_settings_collection = db["user_settings"]
    global_settings_collection = db["global_settings"]
    print("MongoDB connected successfully")
except Exception as e:
    print(f"MongoDB connection error: {e}")
    # Create dummy collections if MongoDB fails
    class DummyCollection:
        def find_one(self, *args, **kwargs):
            return None
        def update_one(self, *args, **kwargs):
            return None
        def insert_one(self, *args, **kwargs):
            return None
    
    user_settings_collection = DummyCollection()
    global_settings_collection = DummyCollection()
    class DummyDB:
        sent_news = DummyCollection()
    db = DummyDB()

# Initialize Pyrogram client
app = Client("AnimeNewsBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Start webhook in a separate thread
webhook_thread = threading.Thread(target=start_webhook, daemon=True)
webhook_thread.start()

async def escape_markdown_v2(text: str) -> str:
    """Escape markdown v2 special characters"""
    return text

async def send_message_to_user(chat_id: int, message: str, image_url: str = None):
    """Send message to user with optional image"""
    try:
        if image_url:
            await app.send_photo(
                chat_id, 
                image_url,
                caption=message,
            )
        else:
            await app.send_message(chat_id, message)
    except Exception as e:
        print(f"Error sending message: {e}")

@app.on_message(filters.command("start"))
async def start(client, message):
    """Handle /start command"""
    chat_id = message.chat.id
    user_name = message.from_user.username or message.from_user.first_name or "User"
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ᴍᴀɪɴ ʜᴜʙ", url="https://t.me/Bots_Nation"),
            InlineKeyboardButton("ꜱᴜᴩᴩᴏʀᴛ ᴄʜᴀɴɴᴇʟ", url="https://t.me/Bots_Nation_Support"),
        ],
        [
            InlineKeyboardButton("ᴅᴇᴠᴇʟᴏᴩᴇʀ", url="https://t.me/darkxside78"),
        ],
    ])

    caption = (
        f"<b><blockquote>ʙᴀᴋᴋᴀᴀᴀ {user_name}!!!\n\n"
        f"ɪ ᴀᴍ ᴀɴ ᴀɴɪᴍᴇ ɴᴇᴡs ʙᴏᴛ.\n"
        f"ɪ ᴛᴀᴋᴇ ᴀɴɪᴍᴇ ɴᴇᴡs ᴄᴏᴍɪɴɢ ғʀᴏᴍ ʀss ꜰᴇᴇᴅs ᴀɴᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴜᴘʟᴏᴀᴅ ɪᴛ ᴛᴏ ᴍʏ ᴍᴀsᴛᴇʀ's ᴀɴɪᴍᴇ ɴᴇᴡs ᴄʜᴀɴɴᴇʟ.</b></blockquote>"
    )

    try:
        if START_PIC:
            await app.send_photo(
                chat_id, 
                START_PIC,
                caption=caption,
                reply_markup=buttons
            )
        else:
            await app.send_message(
                chat_id,
                caption,
                reply_markup=buttons
            )
    except Exception as e:
        print(f"Error in start command: {e}")
        await app.send_message(chat_id, "Bot started successfully!")

@app.on_message(filters.command("news"))
async def connect_news(client, message):
    """Handle /news command to connect a news channel"""
    chat_id = message.chat.id

    if message.from_user.id not in ADMINS:
        await app.send_message(chat_id, "<b><blockquote>You do not have permission to use this command.</b></blockquote>")
        return
    
    if len(message.text.split()) == 1:
        await app.send_message(chat_id, "<b><blockquote>Please provide a channel ID or username.\nUsage: /news @channel_username or /news -100xxxxxxxxx</b></blockquote>")
        return

    channel_input = " ".join(message.text.split()[1:]).strip()

    try:
        if channel_input.startswith("-100"):
            channel = int(channel_input)
            display = str(channel)
        else:
            channel = channel_input if channel_input.startswith("@") else f"@{channel_input}"
            display = channel

        global_settings_collection.update_one(
            {"_id": "config"},
            {"$set": {"news_channel": channel}},
            upsert=True
        )
        await app.send_message(chat_id, f"<b><blockquote>News channel set to: {display}</b></blockquote>")
    except Exception as e:
        print(f"Error setting news channel: {e}")
        await app.send_message(chat_id, f"<b><blockquote>Error setting news channel: {str(e)}</b></blockquote>")

@app.on_message(filters.command("sendnews"))
async def sendnews_cmd(client, message):
    """Handle /sendnews command to manually send news"""
    chat_id = message.chat.id

    if message.from_user.id not in ADMINS:
        await app.send_message(chat_id, "<b><blockquote>You do not have permission to use this command.</b></blockquote>")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await app.send_message(chat_id, "<b><blockquote>Usage: /sendnews {rss_link} {position_number}\nExample: /sendnews https://myanimelist.net/rss/news.xml 1</b></blockquote>")
        return

    rss_link = args[1]
    try:
        position = int(args[2]) - 1
        if position < 0:
            raise ValueError("Position must be positive")
    except ValueError:
        await app.send_message(chat_id, "<b><blockquote>Task position must be a positive integer.</b></blockquote>")
        return

    config = global_settings_collection.find_one({"_id": "config"})
    if not config or "news_channel" not in config:
        await app.send_message(chat_id, "<b><blockquote>No news channel configured. Use /news to set one first.</b></blockquote>")
        return

    news_channel = config["news_channel"]
    try:
        news_channel = int(news_channel)
    except Exception:
        pass

    try:
        # Parse RSS feed
        feed = feedparser.parse(rss_link)
        if not feed.entries or position >= len(feed.entries):
            await app.send_message(chat_id, "<b><blockquote>No news found at that position or invalid RSS feed.</b></blockquote>")
            return

        entry = feed.entries[position]
        msg, thumbnail_url, link = await format_rss_entry(entry)

        # Send news message
        if thumbnail_url:
            await app.send_photo(
                chat_id=news_channel,
                photo=thumbnail_url,
                caption=msg,
            )
        else:
            await app.send_message(
                chat_id=news_channel,
                text=msg,
                disable_web_page_preview=True
            )

        # Try to extract and send video if available
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    html = await resp.text()
            
            soup = BeautifulSoup(html, "html.parser")
            main_selectors = [
                ".news-body", ".entry-content", "article", "main", "#content", ".content"
            ]
            
            yt_iframe = None
            for sel in main_selectors:
                main_block = soup.select_one(sel)
                if main_block:
                    yt_iframe = main_block.find("iframe", src=lambda s: s and ("youtube.com" in s or "youtube-nocookie.com" in s))
                    if yt_iframe:
                        break
            
            if not yt_iframe:
                yt_iframe = soup.find("iframe", src=lambda s: s and ("youtube.com" in s or "youtube-nocookie.com" in s))
            
            if yt_iframe:
                yt_url = yt_iframe["src"]
                if yt_url.startswith("//"):
                    yt_url = "https:" + yt_url
                elif yt_url.startswith("/"):
                    yt_url = "https://www.youtube.com" + yt_url
                
                yt_url = extract_youtube_watch_url(yt_url)
                
                ydl_opts = {
                    'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                    'outtmpl': f'/tmp/ytvideo_{position}.%(ext)s',
                    'quiet': True,
                    'cookiefile': 'cookies.txt',
                    'merge_output_format': 'mp4',
                }
                
                video_path = None
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(yt_url, download=True)
                        video_path = ydl.prepare_filename(info)
                    
                    video_caption = f"<b><blockquote>{entry.title}</blockquote></b>" if 'title' in entry else 'Premiered Video'
                    await app.send_video(chat_id=news_channel, video=video_path, caption=video_caption)
                except Exception as e:
                    print(f"Error downloading/sending video: {e}")
                finally:
                    if video_path and os.path.exists(video_path):
                        try:
                            os.remove(video_path)
                        except Exception as e:
                            print(f"Error deleting temp video file: {e}")
        except Exception as e:
            print(f"Error processing video: {e}")

        await app.send_message(chat_id, "<b><blockquote>News sent successfully!</b></blockquote>")
    
    except Exception as e:
        print(f"Error in sendnews command: {e}")
        await app.send_message(chat_id, f"<b><blockquote>Error sending news: {str(e)}</b></blockquote>")

# Global set to track sent news entries
sent_news_entries = set()

async def main():
    """Main function to start the bot"""
    try:
        await app.start()
        print("Bot is running...")
        print(f"Bot username: @{app.me.username}")
        print("Webhook server started on port 8000")
        
        # Start the RSS feed loop
        asyncio.create_task(news_feed_loop(app, db, global_settings_collection, [URL_A]))
        
        # Keep the bot running
        await asyncio.Event().wait()
    except Exception as e:
        print(f"Error starting bot: {e}")

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")

from urllib.parse import urlparse, parse_qs
import asyncio
import feedparser
from pyrogram import Client
import aiohttp
from bs4 import BeautifulSoup
import yt_dlp
import os

def extract_youtube_watch_url(yt_url):
    """Extract YouTube watch URL from embed or other formats"""
    try:
        if "youtube.com/embed/" in yt_url:
            video_id = yt_url.split("youtube.com/embed/")[-1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={video_id}"
        elif "youtube.com/watch" in yt_url:
            parsed = urlparse(yt_url)
            v = parse_qs(parsed.query).get("v", [""])[0]
            if v:
                return f"https://www.youtube.com/watch?v={v}"
        return yt_url
    except Exception as e:
        print(f"Error extracting YouTube URL: {e}")
        return yt_url

async def fetch_and_send_news(app: Client, db, global_settings_collection, urls):
    """Fetch and send news from RSS feeds"""
    try:
        config = global_settings_collection.find_one({"_id": "config"})
        if not config or "news_channel" not in config:
            print("No news channel configured")
            return

        news_channel = config["news_channel"]
        try:
            news_channel = int(news_channel)
        except Exception:
            pass

        for url in urls:
            try:
                print(f"Fetching RSS from: {url}")
                feed = await asyncio.to_thread(feedparser.parse, url)
                
                if not feed.entries:
                    print(f"No entries found in feed: {url}")
                    continue

                entry = feed.entries[0]  # Get the latest entry
                entry_id = entry.get('id', entry.get('link'))

                # Check if we already sent this news
                if not hasattr(db, 'sent_news'):
                    # Create the collection if it doesn't exist
                    db.sent_news = db["sent_news"]
                
                if not db.sent_news.find_one({"entry_id": entry_id}):
                    msg, thumbnail_url, link = await format_rss_entry(entry)
                    
                    try:
                        # Send the news message
                        if thumbnail_url:
                            await app.send_photo(
                                chat_id=news_channel, 
                                photo=thumbnail_url, 
                                caption=msg
                            )
                        else:
                            await app.send_message(
                                chat_id=news_channel, 
                                text=msg, 
                                disable_web_page_preview=True
                            )

                        # Mark as sent
                        db.sent_news.insert_one({
                            "entry_id": entry_id, 
                            "title": entry.title if 'title' in entry else '', 
                            "link": link
                        })
                        print(f"Sent news: {entry.title if 'title' in entry else 'No title'}")

                        # Try to extract and send video if available
                        await process_video_content(app, news_channel, entry, link)

                    except Exception as e:
                        print(f"Error sending news message: {e}")
                        
            except Exception as e:
                print(f"Error processing RSS feed {url}: {e}")

    except Exception as e:
        print(f"Error in fetch_and_send_news: {e}")

async def process_video_content(app: Client, news_channel, entry, link):
    """Process and send video content if available"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(link) as resp:
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for YouTube iframes in common content selectors
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
            
            # Download and send video
            await download_and_send_video(app, news_channel, entry, yt_url)
            
    except Exception as e:
        print(f"Error processing video content: {e}")

async def download_and_send_video(app: Client, news_channel, entry, yt_url):
    """Download and send YouTube video"""
    video_path = None
    try:
        ydl_opts = {
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': '/tmp/ytvideo_%(id)s.%(ext)s',
            'quiet': True,
            'cookiefile': './cookies.txt',
            'merge_output_format': 'mp4',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(yt_url, download=True)
            video_path = ydl.prepare_filename(info)
        
        if video_path and os.path.exists(video_path):
            video_caption = f"<b><blockquote>{entry.title}</blockquote></b>" if 'title' in entry else 'Premiered Video'
            await app.send_video(
                chat_id=news_channel, 
                video=video_path, 
                caption=video_caption
            )
            print(f"Sent video for: {entry.title if 'title' in entry else 'No title'}")
        
    except Exception as e:
        print(f"Error downloading/sending video: {e}")
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception as e:
                print(f"Error deleting temp video file: {e}")

async def news_feed_loop(app: Client, db, global_settings_collection, urls):
    """Main loop for fetching news from RSS feeds"""
    print("Starting RSS feed loop...")
    while True:
        try:
            await fetch_and_send_news(app, db, global_settings_collection, urls)
            await asyncio.sleep(300)  # Check every 5 minutes (300 seconds)
        except Exception as e:
            print(f"Error in news feed loop: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retrying

async def get_ann_image(guid_url):
    """Get image from Anime News Network article"""
    def is_valid_img(src):
        return src and src.startswith("http") and "spacer.gif" not in src

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(guid_url) as resp:
                html = await resp.text()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Try to find image in figure tag
        figure = soup.find("figure")
        if figure:
            img_tag = figure.find("img")
            if img_tag:
                src = img_tag.get("data-src") or img_tag.get("src")
                if is_valid_img(src):
                    return src
        
        # Try Open Graph image
        img = soup.find("meta", property="og:image")
        if img and is_valid_img(img.get("content")):
            return img["content"]
        
        # Try first valid image
        img_tag = soup.find("img")
        if img_tag:
            src = img_tag.get("data-src") or img_tag.get("src")
            if is_valid_img(src):
                return src
                
    except Exception as e:
        print(f"Error fetching ANN image: {e}")
    
    return None

async def format_rss_entry(entry):
    """Format RSS entry for Telegram message"""
    try:
        title = entry.title if 'title' in entry else 'No Title'
        summary = entry.summary if 'summary' in entry else ''
        link = entry.link if 'link' in entry else ''
        
        # Get thumbnail URL
        thumbnail_url = None
        if 'media_thumbnail' in entry and entry.media_thumbnail:
            thumbnail_url = entry.media_thumbnail[0]['url']
        
        # Special handling for Anime News Network
        if "animenewsnetwork.com" in link and not thumbnail_url:
            guid_url = entry.get('guid', link)
            thumbnail_url = await get_ann_image(guid_url)
        
        # Clean up summary (remove HTML tags)
        if summary:
            soup = BeautifulSoup(summary, "html.parser")
            summary = soup.get_text().strip()
            # Limit summary length
            if len(summary) > 300:
                summary = summary[:300] + "..."
        
        # Format message
        msg = f"<b><blockquote>{title}</blockquote></b>\n"
        if summary:
            msg += f"<b><blockquote expandable><i>{summary}</i></blockquote></b>\n"
        msg += f"<b><blockquote><a href='{link}'>Read Full News</a></blockquote></b>"
        
        return msg, thumbnail_url, link
        
    except Exception as e:
        print(f"Error formatting RSS entry: {e}")
        return "Error formatting news", None, ""

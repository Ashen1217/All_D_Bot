
import os
import asyncio
import logging
import tempfile
import hashlib
import time
import datetime
import random
import requests
import threading
from IPython.display import display, Javascript
from datetime import timedelta

import nest_asyncio
nest_asyncio.apply()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import required modules
import yt_dlp
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# Telegram API credentials - Replace with your own
API_ID = 25319847  # Replace with your API ID
API_HASH = "d8afb09117e7bfc7d63ae89a2ea60012"  # Replace with your API hash
BOT_TOKEN = "7769209508:AAFxNLZli6De01aElXkypqGqQ8wnQA-sujg"  # Your bot token

# Maximum file sizes
MAX_BOT_API_SIZE = 50 * 1024 * 1024  # 50MB (standard Bot API limit)
MAX_TELETHON_SIZE = 2 * 1024 * 1024 * 1024  # 2GB (standard Telegram limit)

# Keep-alive settings
SESSION_START_TIME = time.time()
ACTIVITY_TIMESTAMP = time.time()
KEEP_ALIVE_INTERVAL = 60 * 5  # 5 minutes
# Store status about our keep-alive mechanism
KEEP_ALIVE_STATUS = {
    'last_ping_time': time.time(),
    'active_downloads': 0,
    'total_downloads': 0,
    'last_browser_ping': time.time(),
    'colab_awake': True
}

# Format file size to human-readable format
def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f} GB"

# Update activity timestamp to prevent timeouts
def update_activity():
    global ACTIVITY_TIMESTAMP
    ACTIVITY_TIMESTAMP = time.time()
    KEEP_ALIVE_STATUS['last_ping_time'] = time.time()

# Store format mappings in memory
FORMAT_CACHE = {}

# Generate short ID for format strings
def generate_format_id(format_str, is_audio=False):
    """Generate a short ID for format string"""
    hash_object = hashlib.md5(format_str.encode())
    short_id = hash_object.hexdigest()[:8]
    FORMAT_CACHE[short_id] = {'format': format_str, 'is_audio': is_audio}
    return short_id

# Function to validate URLs from supported platforms
def is_valid_url(url):
    """Check if the URL is from a supported platform."""
    supported_domains = [
        'youtube.com', 'youtu.be',  # YouTube
        'instagram.com',  # Instagram
        'twitter.com', 'x.com',  # Twitter/X
        'tiktok.com',  # TikTok
        'facebook.com', 'fb.watch',  # Facebook
        'dailymotion.com',  # Dailymotion
        'vimeo.com',  # Vimeo
        'reddit.com',  # Reddit
        'microsoftstream.com', 'web.microsoftstream.com',  # Microsoft Stream
        'streaming.microsoft.com', 'msstream.net', 'sharepoint.com'  # Other Microsoft Stream domains
    ]
    return any(domain in url for domain in supported_domains)

# Microsoft Stream specific functions
async def is_microsoft_stream_url(url):
    """Check if the URL is from Microsoft Stream."""
    microsoft_stream_domains = [
        'microsoftstream.com', 
        'web.microsoftstream.com',
        'streaming.microsoft.com',
        'msstream.net',
        'sharepoint.com/personal'
    ]
    return any(domain in url for domain in microsoft_stream_domains)

# Create Telethon client
client = TelegramClient(StringSession(), API_ID, API_HASH)

# ===== KEEP-ALIVE MECHANISMS =====

# Function to keep Colab browser tab alive by executing JavaScript that pings the page
def keep_browser_alive():
    display(Javascript('''
        function ClickConnect(){
            console.log("Ping to keep Colab alive");
            document.querySelector("#connect").click()
        }
        setInterval(ClickConnect, 60000)
    '''))
    logger.info("Browser keep-alive script initialized")
    
# Periodic task to prevent Colab from disconnecting
def keep_colab_alive_thread():
    while True:
        try:
            # Random computation to keep the runtime active
            size = random.randint(100, 500)
            matrix = [[random.random() for _ in range(size)] for _ in range(size)]
            det_sum = sum(matrix[i][i] for i in range(size))
            
            # Update status
            now = time.time()
            idle_time = now - ACTIVITY_TIMESTAMP
            KEEP_ALIVE_STATUS['last_browser_ping'] = now
            
            # Log status periodically
            logger.info(f"Keep-alive task: Idle for {idle_time:.1f}s, Runtime: {format_runtime(now - SESSION_START_TIME)}")
            
            # Simulate network activity with a simple request
            requests.get("https://www.google.com", timeout=10)
            
            # Sleep for a random interval to make it look more natural
            sleep_time = random.randint(30, 90)
            time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"Error in keep-alive thread: {str(e)}")
            time.sleep(60)

def format_runtime(seconds):
    """Format runtime in seconds to a readable format"""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    update_activity()
    await event.respond(
        "👋 Welcome to the Multi-Platform Media Downloader Bot!\n\n"
        "✅ Send me a link from YouTube, Instagram, Twitter (X), TikTok, Facebook, etc., and I'll download the media for you.\n"
        "✅ Works with videos, photos, reels, shorts, and playlists.\n"
        "✅ Supports resolutions from 144p to 4K (2160p).\n"
        "✅ Can upload files up to 2GB (4GB with Telegram Premium)!"
    )

@client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    update_activity()
    await event.respond(
        "📚 *Multi-Platform Media Downloader Help*\n\n"
        "*How to use*:\n"
        "1. Send a media link from any supported platform\n"
        "2. Select your preferred format (video, audio, or photo)\n"
        "3. Wait for the download and upload\n\n"
        "*Supported Platforms*:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• Twitter/X\n"
        "• TikTok\n"
        "• Facebook\n"
        "• Microsoft Stream/SharePoint\n\n"
        "*Commands*:\n"
        "• /start - Start the bot\n"
        "• /help - Show this message\n"
        "• /status - Check bot and Colab status\n"
        "• /msstream - Instructions for Microsoft Stream\n\n"
        "*Having issues?*\n"
        "Try sending a different link or check if the media is available in your region.",
        parse_mode='Markdown'
    )

@client.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    update_activity()
    
    # Calculate runtime information
    current_time = time.time()
    runtime_seconds = int(current_time - SESSION_START_TIME)
    runtime = timedelta(seconds=runtime_seconds)
    
    # Calculate time remaining (assuming a 12-hour limit)
    max_runtime = 12 * 60 * 60  # 12 hours in seconds
    remaining_seconds = max_runtime - runtime_seconds
    remaining = timedelta(seconds=max(0, remaining_seconds))
    
    # Calculate time until idle timeout
    idle_seconds = int(current_time - ACTIVITY_TIMESTAMP)
    idle = timedelta(seconds=idle_seconds)
    idle_timeout = 90 * 60  # 90 minutes in seconds
    idle_remaining = timedelta(seconds=max(0, idle_timeout - idle_seconds))
    
    # Format dates in UTC
    start_time_str = datetime.datetime.utcfromtimestamp(SESSION_START_TIME).strftime('%Y-%m-%d %H:%M:%S UTC')
    current_time_str = datetime.datetime.utcfromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S UTC')
    estimated_end_str = datetime.datetime.utcfromtimestamp(SESSION_START_TIME + max_runtime).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    # Get download stats
    active_downloads = KEEP_ALIVE_STATUS['active_downloads']
    total_downloads = KEEP_ALIVE_STATUS['total_downloads']
    
    await event.respond(
        "📊 *Bot and Colab Status*\n\n"
        f"🟢 *Runtime*\n"
        f"Session start: {start_time_str}\n"
        f"Current time: {current_time_str}\n"
        f"Runtime: {str(runtime).split('.')[0]}\n"
        f"Estimated remaining: {str(remaining).split('.')[0]}\n"
        f"Estimated end: {estimated_end_str}\n\n"
        f"⏳ *Idle Status*\n"
        f"Idle time: {str(idle).split('.')[0]}\n"
        f"Idle timeout in: {str(idle_remaining).split('.')[0]}\n\n"
        f"📈 *Activity*\n"
        f"Active downloads: {active_downloads}\n"
        f"Total downloads: {total_downloads}\n"
        f"Keep-alive: Active\n\n"
        f"*Note:* Google Colab has a 12-hour limit for continuous runtime and will disconnect after ~90 minutes of inactivity.",
        parse_mode='Markdown'
    )

@client.on(events.NewMessage(pattern='/msstream'))
async def msstream_command(event):
    update_activity()
    
    await event.respond(
        "🔑 *Microsoft Stream/SharePoint Download Instructions*\n\n"
        "To download Microsoft Stream or SharePoint videos, follow these steps:\n\n"
        "1️⃣ Log into Microsoft Stream/SharePoint in your browser\n"
        "2️⃣ Navigate to the video you want to download\n"
        "3️⃣ Press F12 to open browser developer tools\n"
        "4️⃣ Go to Network tab and play the video\n"
        "5️⃣ Look for a request with 'media' or 'videotranscode' in it\n"
        "6️⃣ Right-click and Copy > Copy URL\n"
        "7️⃣ Send the URL to me\n\n"
        "For SharePoint videos, look for URLs containing 'transform/videotranscode'",
        parse_mode='Markdown'
    )

@client.on(events.NewMessage(func=lambda e: is_valid_url(e.text) or "mediap.svc.ms" in e.text or "transform/videotranscode" in e.text))
async def url_handler(event):
    update_activity()
    url = event.text.strip()

    # Show processing message
    status_msg = await event.respond("🔍 Processing link...")

    try:
        # Check if it's a Microsoft Stream URL
        if await is_microsoft_stream_url(url) or "mediap.svc.ms" in url or "transform/videotranscode" in url:
            # Treat it as a Microsoft Stream direct URL
            KEEP_ALIVE_STATUS['active_downloads'] += 1
            video_title = "Microsoft Stream Video"
            
            await ms_stream_direct_download(event, url, video_title, status_msg)
            
            KEEP_ALIVE_STATUS['active_downloads'] -= 1
            KEEP_ALIVE_STATUS['total_downloads'] += 1
            return
        
        # For all other platforms, continue with the existing code
        # Set up yt-dlp options for info extraction
        info_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
        }

        # Extract media information using yt-dlp
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                await status_msg.edit("❌ Could not extract media information. The media might be private or unavailable.")
                return

            # Check if it's a TikTok collection (playlist or user profile)
            if 'tiktok.com' in url and ('@' in url or '/video/' not in url):
                # Handle TikTok collections
                if 'entries' in info and info['entries'] and len(info['entries']) > 0:
                    # Offer to download the entire collection or the first video
                    buttons = [
                        [Button.inline("📂 Download Collection", data=f"collection_{url}")],
                        [Button.inline("📹 First Video", data=f"single_{info['entries'][0]['id']}")],
                        [Button.inline("❌ Cancel", data="cancel")]
                    ]

                    await status_msg.edit(
                        f"📂 This is a TikTok collection with {len(info['entries'])} media files\n\n"
                        f"Choose an option:",
                        buttons=buttons
                    )
                    return

            # Check if it's a playlist (YouTube/Instagram)
            if 'entries' in info and info['entries'] and len(info['entries']) > 0:
                # Handle playlists
                first_media = info['entries'][0]
                if isinstance(first_media, dict) and 'id' in first_media:
                    # Offer to download the first media
                    buttons = [
                        [Button.inline("📹 First Media", data=f"single_{first_media['id']}")],
                        [Button.inline("❌ Cancel", data="cancel")]
                    ]

                    await status_msg.edit(
                        f"📂 This is a playlist with {len(info['entries'])} media files\n\n"
                        f"I can download the first media for you:",
                        buttons=buttons
                    )
                    return

            # Single media processing
            media_title = info.get('title', "Unknown Title")
            media_id = info.get('id', "Unknown")
            duration = info.get('duration')

            # Store media info for callback
            event.client.media_info = {
                'url': url,
                'title': media_title,
                'id': media_id,
                'duration': duration
            }

            # Show format selection dialog
            await show_format_selection(status_msg, url, media_title)

    except Exception as e:
        logger.error(f"Error processing link: {str(e)}")
        await status_msg.edit(f"❌ Error: {str(e)}\n\nPlease try again with a different link.")

async def ms_stream_direct_download(event, url, video_title, status_msg):
    """Download Microsoft Stream videos directly."""
    try:
        update_activity()
        
        # Create a temporary directory for the download
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_filename = os.path.join(temp_dir, "msstream_video.mp4")
            
            # Download progress message
            progress_msg = await event.client.send_message(
                event.chat_id,
                "⏳ Download starting for Microsoft Stream video..."
            )
            
            # Download the file using aiohttp instead of yt-dlp
            import aiohttp
            
            # Download with progress updates
            downloaded = 0
            last_update_time = time.time()
            start_time = time.time()
            
            # Set proper headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        await status_msg.edit(f"❌ Error: HTTP status {response.status}")
                        await progress_msg.delete()
                        return
                    
                    # Get total size
                    total_size = int(response.headers.get('Content-Length', 0))
                    size_text = format_size(total_size)
                    
                    if total_size == 0:
                        await status_msg.edit(
                            "❌ Error: Unable to determine file size. This URL may be expired or requires authentication."
                        )
                        await progress_msg.delete()
                        return
                    
                    # Check if file is too large
                    if total_size > MAX_TELETHON_SIZE:
                        await status_msg.edit(
                            f"❌ File too large: {size_text}\n\n"
                            f"Maximum file size with Telethon is 2GB (4GB for Premium users).\n"
                            f"Try a different video."
                        )
                        await progress_msg.delete()
                        return
                    
                    with open(temp_filename, 'wb') as fd:
                        async for chunk in response.content.iter_chunked(1024 * 16):
                            fd.write(chunk)
                            downloaded += len(chunk)
                            update_activity()  # Update activity with each chunk
                            
                            # Update progress every 3 seconds
                            current_time = time.time()
                            if current_time - last_update_time >= 3:
                                last_update_time = current_time
                                percent = (downloaded / total_size) * 100 if total_size > 0 else 0
                                
                                # Calculate speed
                                elapsed = current_time - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                
                                # Progress bar
                                blocks_filled = int(percent // 10)
                                progress_bar = "▓" * blocks_filled + "░" * (10 - blocks_filled)
                                
                                await progress_msg.edit(
                                    f"⏳ Downloading: {percent:.1f}%\n"
                                    f"[{progress_bar}]\n"
                                    f"Speed: {format_size(speed)}/s"
                                )
            
            # Check if file was downloaded successfully
            if not os.path.exists(temp_filename) or os.path.getsize(temp_filename) == 0:
                await status_msg.edit("❌ Error: Downloaded file is empty or missing.")
                await progress_msg.delete()
                return
                
            file_size = os.path.getsize(temp_filename)
            await progress_msg.edit(f"✅ Download complete! Size: {format_size(file_size)}\nUploading to Telegram...")
            
            # Upload to Telegram
            caption = f"🎬 Microsoft Stream Video\n\nSize: {format_size(file_size)}"
            await event.client.send_file(
                event.chat_id,
                temp_filename,
                caption=caption,
                supports_streaming=True
            )
            
            # Final success message
            await status_msg.edit("✅ Microsoft Stream video downloaded and sent successfully!")
            await progress_msg.delete()
            
    except Exception as e:
        logger.error(f"MS Stream download error: {str(e)}")
        await status_msg.edit(f"❌ Error downloading Microsoft Stream video: {str(e)}")

async def show_format_selection(message, url, media_title):
    """Show available formats for download selection."""
    try:
        update_activity()
        # Clear previous format cache
        global FORMAT_CACHE
        FORMAT_CACHE = {}

        # Check if the URL is from YouTube
        is_youtube = any(domain in url for domain in ['youtube.com', 'youtu.be'])

        if is_youtube:
            # YouTube-specific format selection logic
            standard_resolutions = [2160, 1440, 1080, 720, 480, 360, 240, 144]

            # Get available formats
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                available_resolutions = set()

                # Identify available resolutions
                for fmt in formats:
                    try:
                        height = fmt.get('height')
                        if height:
                            available_resolutions.add(height)
                    except:
                        pass

                # Create buttons for available resolutions
                buttons = []

                for res in standard_resolutions:
                    if res in available_resolutions:
                        format_str = f"bestvideo[height={res}]+bestaudio/best[height={res}]/best"
                        label = f"🔥 {res}p" if res >= 1080 else f"📹 {res}p"

                        # Get file size for this format
                        file_size = None
                        for fmt in formats:
                            if fmt.get('height') == res and fmt.get('filesize'):
                                file_size = fmt.get('filesize')
                                break

                        # Add file size to the label if available
                        if file_size:
                            label += f" ({format_size(file_size)})"

                        # Generate short ID for this format string
                        short_id = generate_format_id(format_str, is_audio=False)
                        buttons.append([Button.inline(label, data=f"fmt_{short_id}")])

                # Add audio-only option
                audio_format = "bestaudio[ext=m4a]/bestaudio"
                audio_id = generate_format_id(audio_format, is_audio=True)
                buttons.append([Button.inline("🎵 Audio Only (MP3)", data=f"fmt_{audio_id}")])

                # Add cancel button
                buttons.append([Button.inline("❌ Cancel", data="cancel")])

                # Update message with format selection
                await message.edit(
                    f"🎥 *{media_title}*\n\n"
                    f"📥 Select download format:\n\n"
                    f"With Telethon, you can download files up to 2GB (or 4GB with Telegram Premium)!",
                    buttons=buttons,
                    parse_mode='Markdown'
                )
        else:
            # For non-YouTube platforms, offer a single download option
            format_str = "best"
            short_id = generate_format_id(format_str, is_audio=False)

            buttons = [
                [Button.inline("📹 Download Video", data=f"fmt_{short_id}")],
                [Button.inline("🎵 Download Audio", data=f"fmt_{generate_format_id('bestaudio', is_audio=True)}")],
                [Button.inline("📷 Download Photo", data=f"fmt_{generate_format_id('best', is_audio=False)}")],
                [Button.inline("❌ Cancel", data="cancel")]
            ]

            await message.edit(
                f"🎥 *{media_title}*\n\n"
                f"📥 Select download format:\n\n"
                f"With Telethon, you can download files up to 2GB (or 4GB with Telegram Premium)!",
                buttons=buttons,
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Error showing formats: {str(e)}")
        await message.edit(f"❌ Error fetching media formats: {str(e)}\n\nTry with a different media.")

@client.on(events.CallbackQuery())
async def callback_handler(event):
    """Handle callback queries from inline buttons."""
    update_activity()
    data = event.data.decode('utf-8')

    # Handle cancel action
    if data == "cancel":
        await event.edit("❌ Download canceled.")
        return

    # Handle format selection
    if data.startswith("fmt_"):
        # Extract short format ID
        short_id = data.split("_")[1]

        # Get media info
        media_info = getattr(event.client, 'media_info', None)

        if not media_info:
            await event.edit("❌ Session expired. Please send the link again.")
            return

        url = media_info.get('url')
        media_title = media_info.get('title')

        # Get the original format string
        format_data = FORMAT_CACHE.get(short_id)
        if not format_data:
            await event.edit("❌ Format information not found. Please try again.")
            return

        format_id = format_data['format']
        is_audio_only = format_data['is_audio']

        # Start download
        KEEP_ALIVE_STATUS['active_downloads'] += 1
        await download_and_send(event, url, format_id, media_title, is_audio_only)
        KEEP_ALIVE_STATUS['active_downloads'] -= 1
        KEEP_ALIVE_STATUS['total_downloads'] += 1

    # Handle single media from playlist
    elif data.startswith("single_"):
        media_id = data.split("_")[1]
        url = f"https://www.youtube.com/watch?v={media_id}"

        # Show fetching message
        await event.edit("🔍 Fetching media information...")

        # Extract media info
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                media_title = info.get('title', "Unknown Title")

                # Store media info
                event.client.media_info = {
                    'url': url,
                    'title': media_title,
                    'id': media_id
                }

                # Show format selection
                await show_format_selection(event.message, url, media_title)

        except Exception as e:
            logger.error(f"Error fetching single media: {str(e)}")
            await event.edit(f"❌ Error: {str(e)}")

    # Handle TikTok collection download
    elif data.startswith("collection_"):
        collection_url = data.split("_")[1]

        # Show downloading message
        await event.edit("📥 Downloading TikTok collection...")
        KEEP_ALIVE_STATUS['active_downloads'] += 1

        try:
            # Create a temporary directory for the download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Set up yt-dlp options for downloading the collection
                ydl_opts = {
                    'format': 'best',
                    'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                }

                # Download progress message
                progress_msg = await event.client.send_message(
                    event.chat_id,
                    "⏳ Downloading collection..."
                )

                # Download the collection
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([collection_url])

                # Find the downloaded files
                downloaded_files = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith(('.mp4', '.jpg', '.png'))]

                if not downloaded_files:
                    await progress_msg.edit("❌ Error: No media files found in the collection.")
                    KEEP_ALIVE_STATUS['active_downloads'] -= 1
                    return

                # Upload each file
                for file_path in downloaded_files:
                    file_size = os.path.getsize(file_path)
                    size_text = format_size(file_size)
                    update_activity()

                    # Check if file is too large even for Telethon
                    if file_size > MAX_TELETHON_SIZE:
                        await progress_msg.edit(
                            f"❌ File too large: {size_text}\n\n"
                            f"Maximum file size with Telethon is 2GB (4GB for Premium users).\n"
                            f"Skipping this media."
                        )
                        continue

                    await progress_msg.edit(f"✅ Download complete! Size: {size_text}\nUploading to Telegram...")

                    # Upload the file
                    caption = f"🎬 {os.path.basename(file_path)}\n\nSize: {size_text}"
                    await event.client.send_file(
                        event.chat_id,
                        file_path,
                        caption=caption,
                        supports_streaming=True
                    )

                # Final success message
                await event.edit("✅ TikTok collection download and upload completed successfully!")
                await progress_msg.delete()
                KEEP_ALIVE_STATUS['total_downloads'] += len(downloaded_files)

        except Exception as e:
            logger.error(f"Error downloading TikTok collection: {str(e)}")
            await event.edit(f"❌ Error: {str(e)}")

        KEEP_ALIVE_STATUS['active_downloads'] -= 1

async def download_and_send(event, url, format_id, media_title, is_audio_only):
    """Download media and send to user."""
    update_activity()
    # Show downloading message
    await event.edit(
        f"📥 Downloading: *{media_title}*\n\n"
        f"Format: {'Audio Only' if is_audio_only else 'Video/Photo'}\n"
        f"⏳ Please wait, this may take a few moments...",
        parse_mode='Markdown'
    )

    try:
        # Create a temporary directory for the download
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set file paths and options
            file_ext = 'mp3' if is_audio_only else 'mp4'
            temp_filename = os.path.join(temp_dir, f"download.{file_ext}")

            # Set up yt-dlp options
            ydl_opts = {
                'format': format_id,
                'outtmpl': temp_filename,
                'quiet': True,
                'no_warnings': True,
            }

            if is_audio_only:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                ydl_opts['merge_output_format'] = 'mp4'

            # Download progress message
            progress_msg = await event.client.send_message(
                event.chat_id,
                "⏳ Download starting..."
            )

            # Download the file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find the downloaded file
            output_path = None
            for file in os.listdir(temp_dir):
                if file.endswith(f'.{file_ext}'):
                    output_path = os.path.join(temp_dir, file)
                    break

            if not output_path or not os.path.exists(output_path):
                await progress_msg.edit("❌ Error: Downloaded file not found.")
                return

            # Check file size
            file_size = os.path.getsize(output_path)
            size_text = format_size(file_size)
            update_activity()

            # Check if file is too large even for Telethon
            if file_size > MAX_TELETHON_SIZE:
                await progress_msg.edit(
                    f"❌ File too large: {size_text}\n\n"
                    f"Maximum file size with Telethon is 2GB (4GB for Premium users).\n"
                    f"Try a lower resolution or shorter media."
                )
                return

            await progress_msg.edit(f"✅ Download complete! Size: {size_text}\nUploading to Telegram...")

            # Progress callback for upload
            upload_start_time = asyncio.get_event_loop().time()
            last_update_time = upload_start_time

            async def progress_callback(current, total):
                nonlocal last_update_time
                current_time = asyncio.get_event_loop().time()
                update_activity()

                # Update only every 3 seconds to avoid flood limits
                if current_time - last_update_time >= 3:
                    last_update_time = current_time

                    # Calculate progress
                    percent = current * 100 / total if total > 0 else 0
                    elapsed = int(current_time - upload_start_time)
                    speed = current / elapsed if elapsed > 0 else 0

                    # Update progress message
                    try:
                        await progress_msg.edit(
                            f"⏫ Uploading: {percent:.1f}%\n"
                            f"Speed: {format_size(speed)}/s\n"
                            f"{format_size(current)} / {format_size(total)}"
                        )
                    except:
                        pass  # Ignore message update errors

            # Upload the file
            caption = f"{'🎵' if is_audio_only else '🎬'} {media_title}\n\nSize: {size_text}"

            if is_audio_only:
                await event.client.send_file(
                    event.chat_id,
                    output_path,
                    caption=caption,
                    progress_callback=progress_callback,
                    attributes=[
                        # Add audio attributes as needed
                    ]
                )
            else:
                await event.client.send_file(
                    event.chat_id,
                    output_path,
                    caption=caption,
                    progress_callback=progress_callback,
                    supports_streaming=True
                )

            # Final success message
            await event.edit("✅ Download and upload completed successfully!")
            await progress_msg.delete()

    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        await event.edit(f"❌ Error: {str(e)}")

# Keep-alive function to prevent Colab idle timeout
async def keep_alive_task():
    """Periodically perform actions to keep Colab from timing out due to inactivity."""
    while True:
        try:
            current_time = time.time()
            idle_time = current_time - ACTIVITY_TIMESTAMP
            runtime = current_time - SESSION_START_TIME
            
            # Only log if idle for more than 5 minutes
            if idle_time > 300:
                logger.info(f"Bot idle for {idle_time/60:.1f} minutes. Runtime: {format_runtime(runtime)}")
                
                # If idle for more than 80 minutes, perform more aggressive keep-alive actions
                if idle_time > 80 * 60:
                    # Perform some computation to keep Colab active
                    logger.info("Performing intensive computation to keep runtime active...")
                    size = 500
                    matrix = [[random.random() for _ in range(size)] for _ in range(size)]
                    # Do matrix calculations which are compute-intensive
                    for i in range(size):
                        for j in range(size):
                            if i != j:
                                matrix[i][j] = matrix[i][j] + matrix[j][i]
                    
                    # Make a web request to signal activity
                    try:
                        requests.get("https://www.google.com", timeout=5)
                    except:
                        pass
            
        except Exception as e:
            logger.error(f"Error in keep-alive task: {str(e)}")
        
        # Sleep for the keep-alive interval
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)

async def main():
    # Initialize keep-alive mechanisms
    logger.info("Initializing keep-alive mechanisms...")
    
    # Start the keep-alive thread
    threading.Thread(target=keep_colab_alive_thread, daemon=True).start()
    
    # Execute browser keep-alive script
    try:
        keep_browser_alive()
    except:
        logger.warning("Could not initialize browser keep-alive (normal if not in Colab)")
    
    # Start the client
    await client.start(bot_token=BOT_TOKEN)
    
    # Print session info
    print(f"Bot started at: {datetime.datetime.utcfromtimestamp(SESSION_START_TIME).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Bot username: @{(await client.get_me()).username}")
    print("Multi-Platform Media Downloader Bot is online!")
    print("Keep-alive mechanisms are active to prevent Colab timeouts!")

    # Start the keep-alive task
    asyncio.create_task(keep_alive_task())
    
    # Additional protection - ping the session every 10 minutes
    @client.on(events.NewMessage(pattern=None))
    async def keep_alive_handler(event):
        update_activity()
    
    # Run the client until disconnected
    await client.run_until_disconnected()

# Run the client
if __name__ == "__main__":
    asyncio.run(main())

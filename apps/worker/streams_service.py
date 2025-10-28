import os
import time
import asyncio
import random
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import json

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("streams_worker")

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Proxy configuration
USE_PROXY = os.getenv("USE_PROXY", "false").lower() in ("1", "true", "yes")
PROXY_URL = os.getenv("PROXY_URL")

# Rate limiting
SPOTIFY_SLEEP = float(os.getenv("SPOTIFY_SLEEP", "0.15"))

# Spotify endpoints
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_PATHFINDER_URL = "https://api-partner.spotify.com/pathfinder/v2/query"

# GraphQL for album data
OPERATION_NAME = "getAlbum"
PERSISTED_HASH = "97dd13a1f28c80d66115a13697a7ffd94fe3bebdb94da42159456e1d82bfee76"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

proxies = None
if USE_PROXY and PROXY_URL:
    proxies = {"http": PROXY_URL, "https": PROXY_URL}
    logger.info("Proxy configured for Spotify requests.")

def send_telegram_alert(message: str):
    """Send alert via Telegram bot if configured."""
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        logger.warning("Telegram credentials not configured")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Telegram alert sent to chat {TELEGRAM_CHAT_ID}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}")

def db_conn():
    """Create database connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def spotify_request_with_retries(method: str, url: str, **kwargs) -> requests.Response:
    """Make Spotify API request with retry logic."""
    if proxies:
        kwargs["proxies"] = proxies
    
    for attempt in range(3):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request to {url} failed (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise
    
    raise requests.exceptions.RequestException(f"All retry attempts to {url} failed")

def get_spotify_token() -> str:
    """Get Spotify access token using client credentials."""
    logger.info("Requesting Spotify access token...")
    
    r = spotify_request_with_retries(
        "post",
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=60
    )
    
    logger.info("Successfully obtained Spotify token")
    return r.json()["access_token"]

def search_track(isrc: str, bearer: str) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """Search for track by ISRC and return (track_id, album_id, track_name, artists)."""
    r = spotify_request_with_retries(
        "get",
        SPOTIFY_SEARCH_URL,
        headers={"Authorization": f"Bearer {bearer}"},
        params={"q": f"isrc:{isrc}", "type": "track", "limit": 5},
        timeout=60
    )
    
    items = r.json().get("tracks", {}).get("items", [])
    if not items:
        return None
    
    # Find exact ISRC match or use first result
    best = None
    for t in items:
        if t.get("external_ids", {}).get("isrc", "").upper() == isrc.upper():
            best = t
            break
    
    if best is None:
        best = items[0]
    
    track_id = best.get("id")
    album_id = best.get("album", {}).get("id")
    track_name = best.get("name")
    artists = [a.get("name") for a in (best.get("artists") or []) if a.get("name")]
    artists_joined = " & ".join(artists) if artists else None
    
    if not (track_id and album_id):
        return None
    
    return track_id, album_id, track_name, artists_joined

async def sniff_tokens() -> Tuple[str, Optional[str]]:
    """Get web tokens from Spotify web player using Playwright."""
    proxy_server = None
    if USE_PROXY and PROXY_URL:
        from urllib.parse import urlparse
        parsed_url = urlparse(PROXY_URL)
        proxy_server = {
            "server": f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port}",
            "username": parsed_url.username,
            "password": parsed_url.password
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
            proxy=proxy_server
        )
        
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        
        fut = asyncio.get_event_loop().create_future()
        
        def on_resp(resp):
            if "/pathfinder/v2/query" in resp.url and resp.status == 200:
                hdrs = resp.request.headers
                auth = hdrs.get("authorization")
                if auth and auth.startswith("Bearer "):
                    tok = auth.split(" ", 1)[1]
                    cli = hdrs.get("client-token")
                    if not fut.done():
                        fut.set_result((tok, cli))
        
        page.on("response", on_resp)
        await page.goto("https://open.spotify.com/")
        
        try:
            return await asyncio.wait_for(fut, timeout=30)
        finally:
            await browser.close()

def fetch_album(album_id: str, web_token: str, client_token: Optional[str]) -> Dict[str, Any]:
    """Fetch album data including playcount using GraphQL."""
    headers = {
        "Authorization": f"Bearer {web_token}",
        "User-Agent": USER_AGENT,
        "content-type": "application/json"
    }
    
    if client_token:
        headers["Client-Token"] = client_token
    
    body = {
        "operationName": OPERATION_NAME,
        "variables": {"locale": "", "offset": 0, "limit": 50, "uri": f"spotify:album:{album_id}"},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": PERSISTED_HASH}},
    }
    
    try:
        r = spotify_request_with_retries("post", SPOTIFY_PATHFINDER_URL, headers=headers, json=body, timeout=30)
        response_json = r.json()
        
        if not response_json.get("data"):
            logger.warning(f"Empty data from Spotify for album {album_id}")
            return {}
        
        return response_json
    except requests.exceptions.RequestException:
        return {}

async def run_streams_collection(user_id: str, day_override: Optional[str] = None):
    """Main worker to collect streaming data for a user."""
    day_iso = day_override or (date.today() - timedelta(days=1)).isoformat()
    
    logger.info(f"Starting streams collection for user {user_id} on {day_iso}")
    
    conn = None
    try:
        # Get authentication tokens
        search_token = get_spotify_token()
        web_token, client_token = await sniff_tokens()
        
        # Connect to database
        conn = db_conn()
        
        with conn.cursor() as cur:
            # Get user's catalogue
            cur.execute("""
                SELECT track_uid, isrc, title, artist 
                FROM track_dim 
                WHERE user_id = %s
            """, (user_id,))
            
            tracks = cur.fetchall()
            logger.info(f"Found {len(tracks)} tracks to process")
            
            processed = 0
            errors = 0
            total_playcount = 0
            
            for track in tracks:
                try:
                    # Search for track info
                    track_info = search_track(track['isrc'], search_token)
                    if not track_info:
                        time.sleep(SPOTIFY_SLEEP)
                        continue
                    
                    track_id, album_id, api_title, api_artist = track_info
                    
                    # Fetch album data with playcount
                    album_data = fetch_album(album_id, web_token, client_token)
                    tracks_data = (album_data.get("data", {})
                                  .get("albumUnion", {})
                                  .get("tracksV2", {})
                                  .get("items", []))
                    
                    playcount = None
                    for item in tracks_data:
                        t = item.get("track")
                        if t and t.get("uri") == f"spotify:track:{track_id}":
                            raw = t.get("playcount")
                            if raw and str(raw).isdigit():
                                playcount = int(raw)
                                break
                    
                    if playcount is not None:
                        # Insert/update stream data
                        cur.execute("""
                            INSERT INTO streams (platform, track_uid, stream_date, playcount, user_id)
                            VALUES ('spotify', %s, %s, %s, %s)
                            ON CONFLICT (platform, track_uid, stream_date)
                            DO UPDATE SET playcount = EXCLUDED.playcount
                        """, (track['track_uid'], day_iso, playcount, user_id))
                        
                        total_playcount += playcount
                        processed += 1
                    
                    time.sleep(SPOTIFY_SLEEP)
                    
                except Exception as e:
                    logger.error(f"Error processing track {track['isrc']}: {e}")
                    errors += 1
            
            conn.commit()
            
            # Refresh materialized view
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY streams_daily_delta")
            conn.commit()
            
            logger.info(f"Completed: processed={processed}, errors={errors}, total_playcount={total_playcount}")
            
            # Send alert if no streams found
            if processed > 0 and total_playcount == 0:
                send_telegram_alert(f"Warning: Streams collection for {day_iso} found 0 total streams")
            
    except Exception as e:
        logger.error(f"Stream collection failed: {e}")
        send_telegram_alert(f"Error in stream collection: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Test run for development
    import sys
    user_id = sys.argv[1] if len(sys.argv) > 1 else "test-user-id"
    asyncio.run(run_streams_collection(user_id))

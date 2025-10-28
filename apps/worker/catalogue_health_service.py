import os
import logging
import time
import random
from datetime import date
from typing import Dict, Any, Optional
import difflib

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("catalogue_health")

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

def db_conn():
    """Create database connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def similar(a: str, b: str) -> float:
    """Return similarity ratio between two strings (case-insensitive)."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

def check_apple_music_api(artist: str, title: str) -> bool:
    """Check if track exists on Apple Music."""
    base_url = "https://itunes.apple.com/search"
    params = {
        'term': f"{artist} {title}",
        'entity': 'musicTrack,album',
        'country': 'GB',
        'limit': 20
    }
    
    for attempt in range(3):
        try:
            logger.info(f"[Apple] Checking for '{title}' by {artist} (Attempt {attempt+1})")
            
            response = requests.get(
                base_url, 
                params=params, 
                timeout=15,
                headers={"User-Agent": USER_AGENT}
            )
            
            if response.status_code == 403:
                # Rate limited - wait and retry
                wait_time = (attempt + 1) * 15 + random.uniform(0, 5)
                logger.warning(f"[Apple] Rate limited. Waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            for result in data.get('results', []):
                result_track = result.get('trackName', '')
                result_album = result.get('collectionName', '')
                result_artist = result.get('artistName', '')
                
                if (similar(result_artist, artist) >= 0.85 and 
                    (similar(result_track, title) >= 0.85 or similar(result_album, title) >= 0.85)):
                    logger.info(f"✅ [Apple] Found match: '{result_track or result_album}'")
                    return True
            
            logger.warning(f"❌ [Apple] No match found for '{title}'")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❗️ [Apple] Network error for '{title}': {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                return False
    
    logger.error(f"❗️ [Apple] Failed to check '{title}' after retries")
    return False

def check_spotify_api(sp_client, artist: str, title: str) -> bool:
    """Check if track exists on Spotify."""
    query = f"track:{title} artist:{artist}"
    logger.info(f"[Spotify] Checking for '{title}' by {artist}")
    
    try:
        results = sp_client.search(q=query, type='track', limit=10)
        
        for item in results.get('tracks', {}).get('items', []):
            item_name = item.get('name', '')
            item_artists = [a.get('name', '') for a in item.get('artists', [])]
            
            if (similar(item_name, title) >= 0.85 and 
                any(similar(a_name, artist) >= 0.85 for a_name in item_artists)):
                logger.info(f"✅ [Spotify] Found match: '{item_name}'")
                return True
        
        logger.warning(f"❌ [Spotify] No match found for '{title}'")
        return False
        
    except Exception as e:
        logger.error(f"❗️ [Spotify] API error for '{title}': {e}")
        return False

def run_catalogue_health_check(user_id: str):
    """Check catalogue health and store results in database."""
    logger.info(f"Starting catalogue health check for user {user_id}")
    
    try:
        # Set up Spotify client
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        
        # Connect to database
        conn = db_conn()
        check_date_iso = date.today().isoformat()
        checked_count = 0
        errors = 0
        
        with conn.cursor() as cur:
            # Get user's catalogue
            cur.execute("""
                SELECT track_uid, isrc, title, artist
                FROM track_dim
                WHERE user_id = %s
            """, (user_id,))
            
            tracks = cur.fetchall()
            logger.info(f"Found {len(tracks)} tracks to check")
            
            for track in tracks:
                title = track['title']
                artist = track['artist']
                
                if not title or not artist:
                    logger.warning(f"Skipping {track['isrc']} - missing metadata")
                    continue
                
                # Check both platforms
                apple_exists = check_apple_music_api(artist, title)
                spotify_exists = check_spotify_api(spotify_client, artist, title)
                
                # Random delay to avoid rate limiting
                time.sleep(random.uniform(1.0, 2.5))
                
                # Store results
                cur.execute("""
                    INSERT INTO catalogue_health_status 
                    (check_date, track_uid, apple_music_status, spotify_status, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (check_date, track_uid)
                    DO UPDATE SET 
                        apple_music_status = EXCLUDED.apple_music_status,
                        spotify_status = EXCLUDED.spotify_status,
                        updated_at = NOW()
                """, (check_date_iso, track['track_uid'], apple_exists, spotify_exists, user_id))
                
                checked_count += 1
                
                # Commit in batches
                if checked_count % 10 == 0:
                    conn.commit()
                    logger.info(f"Progress: {checked_count}/{len(tracks)} tracks checked")
            
            conn.commit()
            logger.info(f"Catalogue health check completed: {checked_count} tracks checked, {errors} errors")
            
    except Exception as e:
        logger.error(f"Catalogue health check failed: {e}")
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
    run_catalogue_health_check(user_id)

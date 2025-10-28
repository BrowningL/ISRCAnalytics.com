import os
import time
import logging
from datetime import date
from typing import List, Dict, Any, Optional

import requests
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("playlist_followers")

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_SLEEP = float(os.getenv("SPOTIFY_SLEEP", "0.15"))

# Spotify endpoints
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_PLAYLIST_URL = "https://api.spotify.com/v1/playlists/"

def db_conn():
    """Create database connection."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def get_spotify_token() -> str:
    """Get Spotify access token using client credentials."""
    r = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=60
    )
    r.raise_for_status()
    return r.json()["access_token"]

def get_playlist_followers(playlist_id: str, bearer: str) -> Optional[int]:
    """Get follower count for a Spotify playlist."""
    url = f"{SPOTIFY_PLAYLIST_URL}{playlist_id}"
    headers = {"Authorization": f"Bearer {bearer}"}
    params = {"fields": "followers.total"}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code == 200:
            return r.json().get("followers", {}).get("total", 0)
        elif r.status_code == 404:
            logger.warning(f"Playlist not found: {playlist_id}")
            return None
        else:
            logger.error(f"API error {r.status_code} for playlist {playlist_id}")
            return None
    except Exception as e:
        logger.error(f"Error fetching playlist {playlist_id}: {e}")
        return None

def run_playlist_followers_collection(user_id: str, day_override: Optional[str] = None):
    """Collect follower counts for all user's playlists."""
    day_iso = day_override or date.today().isoformat()
    logger.info(f"Starting playlist followers collection for user {user_id} on {day_iso}")
    
    conn = None
    try:
        # Get Spotify token
        bearer = get_spotify_token()
        
        # Connect to database
        conn = db_conn()
        
        with conn.cursor() as cur:
            # Get user's playlists
            cur.execute("""
                SELECT playlist_uid, playlist_id, playlist_name 
                FROM user_playlists 
                WHERE user_id = %s AND platform = 'spotify'
            """, (user_id,))
            
            playlists = cur.fetchall()
            logger.info(f"Found {len(playlists)} playlists to process")
            
            processed = 0
            errors = 0
            
            for playlist in playlists:
                playlist_id = playlist['playlist_id']
                
                # Extract ID from URI if needed
                if playlist_id.startswith("spotify:playlist:"):
                    playlist_id = playlist_id.split(":")[-1]
                
                # Get follower count
                followers = get_playlist_followers(playlist_id, bearer)
                
                if followers is not None:
                    # Insert follower data
                    cur.execute("""
                        INSERT INTO playlist_followers (platform, playlist_uid, snapshot_date, followers, user_id)
                        VALUES ('spotify', %s, %s, %s, %s)
                        ON CONFLICT (platform, playlist_uid, snapshot_date)
                        DO UPDATE SET followers = EXCLUDED.followers
                    """, (playlist['playlist_uid'], day_iso, followers, user_id))
                    
                    processed += 1
                    logger.info(f"Playlist {playlist['playlist_name']}: {followers} followers")
                else:
                    errors += 1
                
                time.sleep(SPOTIFY_SLEEP)
            
            conn.commit()
            logger.info(f"Completed: processed={processed}, errors={errors}")
            
    except Exception as e:
        logger.error(f"Playlist followers collection failed: {e}")
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
    run_playlist_followers_collection(user_id)

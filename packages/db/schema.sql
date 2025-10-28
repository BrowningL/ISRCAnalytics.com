-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "timescaledb";

-- Users table (managed by Supabase Auth, but we reference it)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Platform dimension table
CREATE TABLE IF NOT EXISTS platform_dim (
    platform TEXT PRIMARY KEY CHECK (platform IN ('spotify', 'apple_music'))
);

INSERT INTO platform_dim VALUES ('spotify'), ('apple_music') ON CONFLICT DO NOTHING;

-- User's track catalogue (multi-tenant)
CREATE TABLE IF NOT EXISTS track_dim (
    track_uid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    isrc TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    release_date DATE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, isrc)
);

CREATE INDEX idx_track_dim_user_id ON track_dim(user_id);
CREATE INDEX idx_track_dim_isrc ON track_dim(isrc);

-- Streams table (hypertable for time-series data)
CREATE TABLE IF NOT EXISTS streams (
    platform TEXT NOT NULL REFERENCES platform_dim(platform),
    track_uid UUID NOT NULL REFERENCES track_dim(track_uid) ON DELETE CASCADE,
    stream_date DATE NOT NULL,
    playcount BIGINT NOT NULL DEFAULT 0,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (platform, track_uid, stream_date)
);

-- Convert to hypertable
SELECT create_hypertable('streams', 'stream_date', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX idx_streams_user_id ON streams(user_id);
CREATE INDEX idx_streams_track_date ON streams(track_uid, stream_date DESC);

-- User's playlists
CREATE TABLE IF NOT EXISTS user_playlists (
    playlist_uid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL REFERENCES platform_dim(platform),
    playlist_id TEXT NOT NULL,
    playlist_name TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, platform, playlist_id)
);

CREATE INDEX idx_user_playlists_user_id ON user_playlists(user_id);

-- Playlist followers (hypertable)
CREATE TABLE IF NOT EXISTS playlist_followers (
    platform TEXT NOT NULL,
    playlist_uid UUID NOT NULL REFERENCES user_playlists(playlist_uid) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    followers INTEGER NOT NULL DEFAULT 0,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (platform, playlist_uid, snapshot_date)
);

SELECT create_hypertable('playlist_followers', 'snapshot_date', if_not_exists => TRUE);

CREATE INDEX idx_playlist_followers_user_id ON playlist_followers(user_id);

-- Catalogue health status
CREATE TABLE IF NOT EXISTS catalogue_health_status (
    check_date DATE NOT NULL,
    track_uid UUID NOT NULL REFERENCES track_dim(track_uid) ON DELETE CASCADE,
    apple_music_status BOOLEAN NOT NULL DEFAULT FALSE,
    spotify_status BOOLEAN NOT NULL DEFAULT FALSE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (check_date, track_uid)
);

CREATE INDEX idx_catalogue_health_user_id ON catalogue_health_status(user_id);

-- Lag tracking tables
CREATE TABLE IF NOT EXISTS daily_totals (
    day DATE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_delta BIGINT NOT NULL DEFAULT 0,
    finalized BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (day, user_id)
);

CREATE TABLE IF NOT EXISTS lag_credits (
    day DATE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    moved_today BIGINT NOT NULL DEFAULT 0,
    moved_alltime BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (day, user_id)
);

-- Materialized view for daily stream deltas (per user)
CREATE MATERIALIZED VIEW IF NOT EXISTS streams_daily_delta AS
WITH stream_data AS (
    SELECT 
        s.user_id,
        s.platform,
        s.track_uid,
        s.stream_date,
        s.playcount,
        t.isrc,
        t.title,
        t.artist,
        LAG(s.playcount) OVER (
            PARTITION BY s.track_uid, s.platform, s.user_id 
            ORDER BY s.stream_date
        ) AS prev_playcount
    FROM streams s
    JOIN track_dim t ON t.track_uid = s.track_uid
)
SELECT 
    user_id,
    platform,
    track_uid,
    stream_date,
    isrc,
    title,
    artist,
    playcount,
    GREATEST(0, playcount - COALESCE(prev_playcount, 0)) AS daily_delta
FROM stream_data;

CREATE UNIQUE INDEX ON streams_daily_delta (user_id, platform, track_uid, stream_date);
CREATE INDEX ON streams_daily_delta (user_id, stream_date DESC);

-- View for playlist followers delta
CREATE VIEW playlist_followers_delta AS
SELECT 
    pf.user_id,
    pf.platform,
    pf.playlist_uid,
    up.playlist_id,
    up.playlist_name,
    pf.snapshot_date AS date,
    pf.followers,
    pf.followers - LAG(pf.followers) OVER (
        PARTITION BY pf.playlist_uid, pf.user_id 
        ORDER BY pf.snapshot_date
    ) AS delta
FROM playlist_followers pf
JOIN user_playlists up ON up.playlist_uid = pf.playlist_uid;

-- Daily aggregated streams view
CREATE VIEW spotify_streams_daily_adjusted AS
SELECT 
    user_id,
    stream_date AS date,
    SUM(daily_delta)::BIGINT AS delta
FROM streams_daily_delta
WHERE platform = 'spotify'
GROUP BY user_id, stream_date;

-- Function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_streams_delta()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY streams_daily_delta;
END;
$$ LANGUAGE plpgsql;

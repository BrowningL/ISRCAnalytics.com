# Deployment Guide for ISRCAnalytics.com

## Prerequisites

- Railway.app account
- Supabase account (for auth)
- Spotify Developer account
- TimescaleDB instance (Railway or external)
- Domain name (optional)

## Step 1: Database Setup

### 1.1 Create TimescaleDB on Railway

1. Create new project in Railway
2. Add TimescaleDB plugin from marketplace
3. Note the DATABASE_URL from the plugin settings

### 1.2 Run Database Migrations

```bash
# Connect to database
psql $DATABASE_URL

# Run schema.sql
\i packages/db/schema.sql
```

## Step 2: Supabase Auth Setup

1. Create new Supabase project
2. Go to Settings > API
3. Copy:
   - Project URL → NEXT_PUBLIC_SUPABASE_URL
   - Anon public key → NEXT_PUBLIC_SUPABASE_ANON_KEY
   - Service role key → SUPABASE_SERVICE_KEY

4. Configure Auth providers (optional):
   - Enable Email/Password
   - Configure OAuth providers (Google, GitHub, etc.)

## Step 3: Spotify API Setup

1. Go to https://developer.spotify.com/dashboard
2. Create new app
3. Copy:
   - Client ID → SPOTIFY_CLIENT_ID
   - Client Secret → SPOTIFY_CLIENT_SECRET

## Step 4: Railway Deployment

### 4.1 Create Railway Project

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Create project
railway init
```

### 4.2 Configure Services

Create three services in Railway:

1. **Web (Next.js)**
   ```
   Build Command: cd apps/web && npm install && npm run build
   Start Command: cd apps/web && npm start
   Port: 3000
   ```

2. **API (Go)**
   ```
   Build Command: cd apps/api && go build -o api ./cmd/main.go
   Start Command: ./apps/api/api
   Port: 8080
   ```

3. **Worker (Python)**
   ```
   Builder: Docker
   Dockerfile Path: apps/worker/Dockerfile
   ```

### 4.3 Environment Variables

Add to Railway project settings:

```env
# Database
DATABASE_URL=<from-timescaledb-plugin>

# Supabase
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_KEY=<your-service-key>

# Spotify
SPOTIFY_CLIENT_ID=<your-client-id>
SPOTIFY_CLIENT_SECRET=<your-client-secret>

# API URLs
NEXT_PUBLIC_API_URL=https://api-<your-project>.railway.app/api

# JWT Secret
JWT_SECRET=<generate-random-secret>

# Worker Config
ENABLE_SCHEDULER=true
SCHEDULE_EVERY_HOURS=6
SPOTIFY_SLEEP=0.15

# Optional
TELEGRAM_BOT_TOKEN=<optional>
TELEGRAM_CHAT_ID=<optional>
USE_PROXY=false
```

### 4.4 Deploy

```bash
# Deploy all services
railway up

# Or deploy individually
railway up -s web
railway up -s api
railway up -s worker
```

## Step 5: Domain Configuration

1. Go to Railway project settings
2. Add custom domain to web service
3. Configure DNS:
   - CNAME: isrcanalytics.com → <railway-domain>
   - CNAME: www.isrcanalytics.com → <railway-domain>
   - CNAME: api.isrcanalytics.com → <api-railway-domain>

## Step 6: Post-Deployment

### 6.1 Test Health Endpoints

```bash
# Test API
curl https://api.isrcanalytics.com/api/health

# Test Worker
curl https://worker.isrcanalytics.com/
```

### 6.2 Initialize First User

1. Sign up through web interface
2. Add user to database if needed:

```sql
INSERT INTO users (email) VALUES ('admin@isrcanalytics.com');
```

### 6.3 Schedule First Data Collection

```bash
# Trigger manual collection
curl -X POST https://worker.isrcanalytics.com/run \
  -H "Content-Type: application/json" \
  -H "x-automation-token: <your-token>" \
  -d '{"user_id": "<user-uuid>"}'
```

## Monitoring

### Railway Logs

```bash
# View logs
railway logs -s web
railway logs -s api
railway logs -s worker
```

### Database Monitoring

```sql
-- Check recent streams
SELECT * FROM streams 
WHERE user_id = '<user-id>' 
ORDER BY stream_date DESC 
LIMIT 10;

-- Check materialized view
SELECT * FROM streams_daily_delta 
WHERE user_id = '<user-id>' 
ORDER BY stream_date DESC 
LIMIT 10;
```

## Scaling

### Horizontal Scaling

In railway.json, adjust replicas:

```json
{
  "deploy": {
    "numReplicas": 3,
    "multiRegionConfig": {
      "us-west1": {"numReplicas": 2},
      "europe-west4": {"numReplicas": 1}
    }
  }
}
```

### Database Optimization

```sql
-- Add compression policy
SELECT add_compression_policy('streams', INTERVAL '7 days');

-- Add retention policy
SELECT add_retention_policy('streams', INTERVAL '1 year');

-- Continuous aggregates for better performance
CREATE MATERIALIZED VIEW daily_streams_summary
WITH (timescaledb.continuous) AS
SELECT 
  user_id,
  time_bucket('1 day', stream_date) AS day,
  SUM(playcount) as total_plays
FROM streams
GROUP BY user_id, day;
```

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Check DATABASE_URL format
   - Verify network access
   - Check connection pool settings

2. **Auth not working**
   - Verify Supabase keys
   - Check CORS settings
   - Verify JWT configuration

3. **Worker not collecting data**
   - Check Spotify credentials
   - Verify proxy settings if using
   - Check worker logs for errors

4. **Slow queries**
   - Refresh materialized views
   - Check indexes
   - Consider partitioning large tables

## Security Checklist

- [ ] Environment variables secured
- [ ] Database access restricted
- [ ] API rate limiting configured
- [ ] CORS properly configured
- [ ] JWT secrets rotated regularly
- [ ] SSL/TLS enabled on all endpoints
- [ ] Regular backups configured
- [ ] Monitoring alerts set up

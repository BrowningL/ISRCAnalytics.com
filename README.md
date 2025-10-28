# ISRCAnalytics.com

A modern SaaS platform for tracking music streaming data across Spotify and Apple Music, with detailed analytics, playlist tracking, and catalogue health monitoring.

## Architecture

- **Frontend**: Next.js 14 with TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: Go API with pgx for PostgreSQL
- **Database**: TimescaleDB (time-series PostgreSQL)
- **Workers**: Python services for data collection
- **Auth**: Supabase Auth with JWT

## Project Structure

```
isrc-analytics/
├── apps/
│   ├── web/          # Next.js dashboard
│   ├── api/          # Go backend
│   └── worker/       # Python services
├── packages/
│   └── db/           # Database schema
└── docker-compose.yml
```

## Features

- Real-time streaming analytics
- Playlist follower tracking
- Catalogue health monitoring
- Multi-tenant architecture
- Automated data collection
- Beautiful dashboard with charts

## Quick Start

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in credentials
3. Run `docker-compose up -d` for local TimescaleDB
4. Run database migrations
5. Start services with `pnpm dev`

## Deployment

Optimized for Railway.app deployment with automatic scaling and multi-region support.

# YouTube integration

YouTube is an independent source family. It uses the official YouTube Data API
for channel/video metadata and the YouTube Analytics API for reporting data.

## Google configuration

Create a Google Cloud project, enable **YouTube Data API v3** and **YouTube
Analytics API**, configure the OAuth consent screen, and create a Web OAuth
client. The redirect URI must exactly match `YOUTUBE_REDIRECT_URI`.

Backend-only values are:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REDIRECT_URI`
- `YOUTUBE_ACCESS_TOKEN` (short-lived operational token)
- `YOUTUBE_REFRESH_TOKEN` (long-lived credential used to refresh access)
- `YOUTUBE_DATA_API_BASE_URL` and `YOUTUBE_ANALYTICS_API_BASE_URL` (optional)

Use the least privilege scopes needed by the deployment, normally
`https://www.googleapis.com/auth/youtube.readonly` and
`https://www.googleapis.com/auth/yt-analytics.readonly`. Google consent,
verification, and quota rules apply to the project. Secrets and tokens never
enter frontend responses, AI context, semantic metadata, or logs.

After `POST /api/v1/youtube/connect`, explicitly map each discovered channel
with `POST /api/v1/youtube/mappings`. Run incremental sync or bounded backfill
with `POST /api/v1/youtube/sync`. Daily records are upserted by organization,
channel/video, and reporting date. Recent periods should be re-synced using a
lookback window because analytics can change.

Shorts are stored as `content_type=unknown` unless the official API provides a
reliable classification; duration heuristics are not used. YouTube data is
available to the existing generic `business.query` through `ai_youtube_*`
views. No YouTube-to-sale attribution is created.

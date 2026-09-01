# Meta and Instagram integration

Meta is an independent marketing source family. It is never merged into
SmartUp, canonical sales, or sale attribution.

## Configuration

Set these backend-only environment variables (never put them in frontend
configuration or logs):

- `META_APP_ID`
- `META_APP_SECRET`
- `META_REDIRECT_URI`
- `META_GRAPH_API_VERSION` (a Graph API version supported by the Meta app)
- `META_ACCESS_TOKEN` for the local deployment credential boundary
- `META_GRAPH_API_BASE_URL` (optional, defaults to `https://graph.facebook.com`)

For production, replace the access-token environment binding with the existing
server-side secret manager. The API never accepts or returns a token.

Create a Meta app in Meta for Developers, configure the OAuth redirect URI to
the exact `META_REDIRECT_URI`, and request only permissions approved for the
connected account. Typical permissions are `ads_read`, `business_management`,
`pages_show_list`, `pages_read_engagement`, `read_insights`, `instagram_basic`,
and `instagram_manage_insights`; availability and App Review requirements
depend on the account type and Graph API version.

## Usage

An owner calls `POST /api/v1/meta/connect` to discover ad accounts, Facebook
Pages, and linked Instagram accounts. The owner explicitly maps each resource
with `POST /api/v1/meta/mappings`, including an AI Business OS
`organization_id`. Then `POST /api/v1/meta/sync` runs an incremental sync or a
bounded backfill (`mode=backfill`, `backfill_days=30`). Repeating either call
is idempotent for normalized records and does not create duplicate daily
insights.

The current integration uses the official Graph API discovery, hierarchy,
posts, and insights edges. Unsupported metrics are left null. Account currency
and reporting timezone remain attached to the source account; values from
different currencies must not be summed without an explicit FX source.

Marketing data is exposed to the existing generic `business.query` only via
the allowlisted `ai_*` views. No Meta token, secret, or raw authorization
header is included in those views or in AI context. No Meta/Instagram to
canonical-sale attribution relationship is created.

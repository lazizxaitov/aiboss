# Marketing attribution foundation

Attribution is evidence-first. A Meta action, Instagram interaction, or
YouTube view is a platform fact, not a canonical sale. A same-day change,
similar name, amount, or AI hypothesis creates correlation only and never an
attributed outcome.

Confirmed evidence is ingested through the authenticated owner endpoint
`POST /api/v1/marketing/attribution/evidence`. The backend validates the
source entity in mapped Meta/Instagram/Facebook/YouTube data, validates the
canonical target in the same `organization_id`, and idempotently stores the
link. Supported evidence types include explicit tracking IDs, click IDs,
campaign parameters, platform conversion references, first-party sessions or
leads, first-party order links, and imported conversion links.

Only confirmed evidence is projected into
`ai_marketing_attribution_evidence` and
`ai_marketing_attributed_outcomes`. Tracking fields are kept out of AI-safe
views; secrets, tokens and authorization headers are never stored there.

Platform ROAS and confirmed business ROAS remain separate. Cross-source trend
comparisons are allowed, but without linkage the result must be described as a
correlation or hypothesis and may recommend adding UTM/session/order tracking.
Future website, CRM, Google Ads or TikTok sources can write the same generic
evidence contract without a new Agent Core.

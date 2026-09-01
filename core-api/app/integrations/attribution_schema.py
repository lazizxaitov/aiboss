ATTRIBUTION_TABLES = {
    "marketing_attribution_evidence": ("id", "organization_id", "source_platform", "source_entity_type", "source_entity_id", "target_entity_type", "target_entity_id", "evidence_type", "confidence", "occurred_at", "attribution_window", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "click_id_hash", "provenance", "created_at", "updated_at"),
    "marketing_attributed_outcomes": ("id", "organization_id", "evidence_id", "source_platform", "source_entity_type", "source_entity_id", "sale_id", "revenue", "currency", "occurred_at", "created_at", "updated_at"),
}
_UNIQUE = {"marketing_attribution_evidence": "UNIQUE (organization_id, source_platform, source_entity_type, source_entity_id, target_entity_type, target_entity_id, evidence_type)", "marketing_attributed_outcomes": "UNIQUE (organization_id, evidence_id, sale_id)"}
ATTRIBUTION_DDL = tuple(f"CREATE TABLE IF NOT EXISTS {table} (" + ", ".join(f"{column} {'uuid' if column in {'id', 'organization_id', 'evidence_id', 'sale_id'} else 'text'}" for column in columns) + f", PRIMARY KEY (id), {_UNIQUE[table]})" for table, columns in ATTRIBUTION_TABLES.items())
ATTRIBUTION_VIEW_DEFINITIONS = {
    "ai_marketing_attribution_evidence": "SELECT organization_id, source_platform, source_entity_type, source_entity_id, target_entity_type, target_entity_id, evidence_type, confidence, occurred_at, attribution_window, provenance FROM marketing_attribution_evidence",
    "ai_marketing_attributed_outcomes": "SELECT organization_id, evidence_id, source_platform, source_entity_type, source_entity_id, sale_id, revenue, currency, occurred_at FROM marketing_attributed_outcomes",
}
ATTRIBUTION_VIEW_COLUMNS = {name: tuple(item.strip() for item in definition.split("SELECT ", 1)[1].split(" FROM ", 1)[0].split(",")) for name, definition in ATTRIBUTION_VIEW_DEFINITIONS.items()}

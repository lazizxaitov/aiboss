export type DashboardCard = {
  label: string;
  value: string;
  note: string;
  detailsHref?: string | null;
  status?: "available" | "partial" | "unavailable" | "syncing" | "error";
  previous_value?: string | null;
  change?: string | null;
};

export type TelegramLinkedUser = {
  chat_id: string;
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
  linked_at?: string | null;
};

export type TelegramLinkStatus = {
  connected: boolean;
  chats: string[];
  users: TelegramLinkedUser[];
  token?: string | null;
  deep_link?: string | null;
  qr_data_uri?: string | null;
  instructions?: string | null;
  expires_at?: string | null;
};

export async function getTelegramLinkStatus(): Promise<TelegramLinkStatus> {
  return requestJson<TelegramLinkStatus>("/api/v1/telegram/link/status", {}, fastReadTimeoutMs);
}

export async function createTelegramLink(): Promise<TelegramLinkStatus> {
  return requestJson<TelegramLinkStatus>("/api/v1/telegram/link/create", { method: "POST" });
}

export async function disconnectTelegram(): Promise<TelegramLinkStatus> {
  return requestJson<TelegramLinkStatus>("/api/v1/telegram/link/disconnect", { method: "POST" });
}

export async function disconnectTelegramChat(chatId: string): Promise<TelegramLinkStatus> {
  return requestJson<TelegramLinkStatus>("/api/v1/telegram/link/disconnect-chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId }),
  });
}

export type DeviceLinkResult = {
  token?: string | null;
  deep_link?: string | null;
  qr_data_uri?: string | null;
  expires_at?: string | null;
};

export type PairedDevice = {
  device_id: string;
  label: string;
  user_agent?: string | null;
  linked_at?: string | null;
};

export async function createDeviceLink(origin: string): Promise<DeviceLinkResult> {
  return requestJson<DeviceLinkResult>("/api/v1/device/link/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin }),
  });
}

export async function getPairedDevices(): Promise<PairedDevice[]> {
  const response = await requestJson<{ devices: PairedDevice[] }>("/api/v1/device/link/list", {}, fastReadTimeoutMs);
  return response.devices;
}

export async function transcribeVoiceMessage(blob: Blob, filename: string): Promise<string> {
  const form = new FormData();
  form.append("audio", blob, filename);
  const token = ownerSessionToken();
  const response = await fetch(`${coreApiBaseUrl}/api/v1/ai/transcribe`, {
    method: "POST",
    // No Content-Type here on purpose — the browser must set its own
    // multipart boundary for FormData, which authenticatedHeaders() would
    // otherwise override with "application/json" and break the upload.
    headers: token ? { Authorization: `Bearer ${decodeURIComponent(token)}` } : {},
    body: form,
  });
  const payload = (await response.json().catch(() => ({}))) as { text?: string; detail?: string };
  if (!response.ok || typeof payload.text !== "string") {
    throw new Error(payload.detail ?? "Не удалось распознать голосовое сообщение");
  }
  return payload.text;
}

export async function disconnectDevice(deviceId: string): Promise<PairedDevice[]> {
  const response = await requestJson<{ devices: PairedDevice[] }>("/api/v1/device/link/disconnect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId }),
  });
  return response.devices;
}

export type DashboardMetric = DashboardCard;

export type DashboardSignal = {
  severity?: string;
  title: string;
  badge: string;
  note: string;
  organization?: string | null;
  period?: string | null;
  detailsHref?: string | null;
  metrics?: string[];
};

export type DashboardTrend = {
  title: string;
  description: string;
  badge: string;
  labels: string[];
  values: number[];
};

export type DashboardStructureItem = {
  label: string;
  value: string;
  note: string;
  color: string;
};

export type DashboardAvailabilityCard = {
  label: string;
  value: string;
  note: string;
  status: "available" | "partial" | "unavailable" | "syncing" | "error";
  detailsHref?: string | null;
};

export type DashboardOverviewResponse = {
  generated_at: string;
  analysis_engine: string;
  analysis_note: string;
  freshness: string;
  data_summary: DashboardCard[];
  executive_summary: DashboardCard[];
  business_metrics: DashboardMetric[];
  trend: DashboardTrend;
  signals: DashboardSignal[];
  action_center: DashboardSignal[];
  structure: DashboardStructureItem[];
  businesses: DashboardBusinessBreakdown[];
  organization_performance: DashboardBusinessBreakdown[];
  recent_sales: DashboardRecentSale[];
  top_products: DashboardTopProduct[];
  inventory: DashboardInventoryCard[];
  recent_payments: DashboardPaymentCard[];
  dead_stock: DashboardTopProduct[];
  returns_summary: DashboardCard[];
  cash_flow: DashboardCard[];
  customers_summary: DashboardCard[];
  seller_performance: DashboardCard[];
  recommendations: DashboardCard[];
  availability: DashboardAvailabilityCard[];
  ai_insights: string[];
};

export type DashboardOverviewFilters = {
  businessId?: string;
  period?: "all" | "30d" | "90d" | "12m";
  channel?: "meta_ads" | "youtube" | "telegram" | "other";
};

export type MetaResource = { id?: string; resource_type: string; external_id: string; name?: string | null; username?: string | null; currency?: string | null; timezone?: string | null };
export type MetaStatus = { status: string; configured: boolean; last_success_at?: string | null; last_error?: string | null; resources: MetaResource[]; mappings: Array<{ organization_id: string; resource_type: string; external_id: string }> };

export async function getMetaStatus(): Promise<MetaStatus> {
  return requestJson<MetaStatus>("/api/v1/meta/status", {}, fastReadTimeoutMs);
}
export async function connectMeta(): Promise<MetaStatus> {
  return requestJson<MetaStatus>("/api/v1/meta/connect", { method: "POST" });
}
export async function mapMetaResource(payload: { organization_id: string; resource_type: string; external_id: string; display_name?: string }): Promise<unknown> {
  return requestJson<unknown>("/api/v1/meta/mappings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export async function syncMeta(mode: "incremental" | "backfill" = "incremental", backfillDays = 7): Promise<MetaStatus & { sync_status?: string }> {
  return requestJson<MetaStatus & { sync_status?: string }>("/api/v1/meta/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, backfill_days: backfillDays }) });
}

export type YouTubeStatus = { status: string; configured: boolean; last_success_at?: string | null; last_error?: string | null; channels: Array<{ external_id: string; title?: string | null; subscriber_count?: string | null; video_count?: string | null }>; mappings: Array<{ organization_id: string; channel_id: string }> };
export async function getYouTubeStatus(): Promise<YouTubeStatus> { return requestJson<YouTubeStatus>("/api/v1/youtube/status", {}, fastReadTimeoutMs); }
export async function connectYouTube(): Promise<YouTubeStatus> { return requestJson<YouTubeStatus>("/api/v1/youtube/connect", { method: "POST" }); }
export async function mapYouTubeChannel(payload: { organization_id: string; channel_id: string; display_name?: string }): Promise<unknown> { return requestJson<unknown>("/api/v1/youtube/mappings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); }
export async function syncYouTube(mode: "incremental" | "backfill" = "incremental", backfillDays = 7): Promise<YouTubeStatus & { sync_status?: string }> { return requestJson<YouTubeStatus & { sync_status?: string }>("/api/v1/youtube/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, backfill_days: backfillDays }) }); }
export type MarketingAttributionStatus = { evidence_available: boolean; confirmed_attribution_available: boolean; evidence_count: number; attributed_outcome_count: number; message: string };
export async function getMarketingAttributionStatus(): Promise<MarketingAttributionStatus> { return requestJson<MarketingAttributionStatus>("/api/v1/marketing/attribution/status", {}, fastReadTimeoutMs); }

export type AnalyticsDataStatus =
  | "AVAILABLE"
  | "PARTIAL"
  | "NO_DATA"
  | "NO_VERIFIED_DATA"
  | "NOT_AVAILABLE"
  | "PERMISSION_RESTRICTED"
  | "UNRESOLVED"
  | "INSUFFICIENT_HISTORY"
  | "NOT_SUPPORTED"
  | "ANALYSIS_PENDING";

export type AnalyticsPeriodPreset =
  | "today"
  | "yesterday"
  | "7d"
  | "30d"
  | "current_month"
  | "previous_month"
  | "custom"
  | "all";

export type AnalyticsComparisonMode =
  | "previous_period"
  | "previous_week"
  | "previous_month"
  | "previous_year";

export type OrganizationContextMode = "all" | "single" | "multiple";

export type OrganizationContext = {
  mode: OrganizationContextMode;
  organization_ids: string[];
};

export type PeriodContext = {
  preset: AnalyticsPeriodPreset;
  date_from: string | null;
  date_to: string | null;
};

export type AnalyticsContextState = {
  organization_context: OrganizationContext;
  period_context: PeriodContext;
  saved_at: string;
};

export type AnalyticsContextUpdate = {
  organization_context?: OrganizationContext;
  period_context?: PeriodContext;
};

export type AnalyticsPeriodWindow = {
  current_start: string | null;
  current_end: string | null;
  previous_start: string | null;
  previous_end: string | null;
  label: string;
  comparison_label: string;
};

export type AnalyticsMetricValue = {
  value: string | number | null;
  previous_value: string | number | null;
  delta: string | number | null;
  percent_delta: string | number | null;
  unit: string;
  status: AnalyticsDataStatus;
  data_status: AnalyticsDataStatus;
  coverage: number | null;
  confidence: number | null;
  currency: string | null;
  record_count: number;
  note: string | null;
};

export type AnalyticsBusinessSummary = {
  revenue: AnalyticsMetricValue;
  orders: AnalyticsMetricValue;
  realised_sales: AnalyticsMetricValue;
  sold_units: AnalyticsMetricValue;
  average_order: AnalyticsMetricValue;
  unique_customers: AnalyticsMetricValue;
  unique_products: AnalyticsMetricValue;
  payments_received: AnalyticsMetricValue;
  customer_return_value: AnalyticsMetricValue;
  current_stock: AnalyticsMetricValue;
  visits: AnalyticsMetricValue;
  verified_cash_in: AnalyticsMetricValue;
  verified_cash_out: AnalyticsMetricValue;
  returns: AnalyticsMetricValue;
  expenses: AnalyticsMetricValue;
  cash_flow: AnalyticsMetricValue;
  customers: AnalyticsMetricValue;
};

export type AnalyticsOrganizationItem = {
  organization_id: string;
  organization_name: string;
  metrics: AnalyticsBusinessSummary;
  comparison: Record<string, AnalyticsMetricValue>;
  products_sold: AnalyticsMetricValue;
  sales_reps: AnalyticsMetricValue;
  visits: AnalyticsMetricValue;
  stock: AnalyticsMetricValue;
  data_status: AnalyticsDataStatus;
};

export type AnalyticsDataQualityEntry = {
  metric_key: string;
  label: string;
  data_status: AnalyticsDataStatus;
  message: string;
  affected_domains: string[];
};

export type AnalyticsDataQualityReport = {
  overall_status: AnalyticsDataStatus;
  items: AnalyticsDataQualityEntry[];
  notes: string[];
};

export type AnalyticsOrganizationReport = {
  period: AnalyticsPeriodWindow;
  items: AnalyticsOrganizationItem[];
  comparison: AnalyticsOrganizationItem[];
  data_quality: AnalyticsDataQualityReport;
};

export type DashboardOrganizationMode = "ALL" | "SINGLE" | "MULTIPLE";

export type DashboardWidgetSourceType = "PERMANENT" | "AI_DYNAMIC" | "USER_PINNED";

export type DashboardSemanticSize = "XS" | "S" | "M" | "L" | "XL";

export type DashboardFlowHint = "horizontal" | "vertical" | "wide";

export type DashboardAspectHint = "compact" | "square" | "wide" | "tall";

export type DashboardContentDensity = "low" | "medium" | "high";

export type DashboardScrollBehavior = "none" | "internal";

export type DashboardWidgetType =
  | "kpi"
  | "trend"
  | "line_chart"
  | "bar_chart"
  | "ranking"
  | "table"
  | "alert"
  | "product_alert"
  | "customer_alert"
  | "inventory_alert"
  | "watchlist"
  | "organization_comparison"
  | "product_ranking"
  | "customer_ranking"
  | "inventory_risk"
  | "visit_summary"
  | "data_quality"
  | "sales_rep_performance"
  | "ai_insight"
  | "ai_recommendation"
  | "photo_alert";

export type DashboardDrilldown = {
  target: string;
  entity_type: string | null;
  entity_id: string | null;
  organization_ids: string[];
  filters: Record<string, string>;
};

export type DashboardManifestWidget = {
  widget_id: string;
  widget_type: DashboardWidgetType;
  source_type: DashboardWidgetSourceType;
  title: string;
  subtitle: string | null;
  metric_keys: string[];
  signal_ids: string[];
  entity_type: string | null;
  entity_id: string | null;
  organization_ids: string[];
  semantic_size: DashboardSemanticSize;
  priority: number;
  priority_reason: string;
  min_size: DashboardSemanticSize;
  preferred_size: DashboardSemanticSize;
  max_size: DashboardSemanticSize;
  supports_horizontal_expand: boolean;
  supports_vertical_expand: boolean;
  supports_internal_scroll: boolean;
  flow: DashboardFlowHint;
  preferred_aspect: DashboardAspectHint;
  content_density: DashboardContentDensity;
  scroll_behavior: DashboardScrollBehavior;
  removable_by_ai: boolean;
  movable_by_ai: boolean;
  resizable_by_ai: boolean;
  locked_position: boolean;
  locked_size: boolean;
  pinned: boolean;
  hidden: boolean;
  drilldown: DashboardDrilldown | null;
  summary: string | null;
  data_status: AnalyticsDataStatus;
  payload: Record<string, unknown>;
};

export type DashboardWidgetCapabilities = {
  min_size: DashboardSemanticSize;
  preferred_size: DashboardSemanticSize;
  max_size: DashboardSemanticSize;
  supports_horizontal_expand: boolean;
  supports_vertical_expand: boolean;
  supports_internal_scroll: boolean;
  flow: DashboardFlowHint;
  preferred_aspect: DashboardAspectHint;
  content_density: DashboardContentDensity;
  scroll_behavior: DashboardScrollBehavior;
};

export type DashboardWidgetRegistryEntry = {
  widget_type: DashboardWidgetType;
  description: string;
  capabilities: DashboardWidgetCapabilities;
  default_metric_keys: string[];
  allowed_source_types: DashboardWidgetSourceType[];
};

export type DashboardLayoutPolicy = {
  manifest_has_no_coordinates: boolean;
  device_independent: boolean;
  preserve_locked_widgets: boolean;
  supports_internal_scroll: boolean;
  permanent_widget_ids: string[];
  notes: string[];
};

export type DashboardManifestDataQuality = {
  overall_status: AnalyticsDataStatus;
  surfaced_items: AnalyticsDataQualityEntry[];
  notes: string[];
};

export type AIProviderStatus = {
  provider_name: string | null;
  model_name: string | null;
  used_fallback: boolean;
  latency_ms: number | null;
  status: string;
  note: string | null;
};

export type DashboardManifestContext = {
  organization_mode: DashboardOrganizationMode;
  organization_ids: string[];
  organization_names: string[];
  period: AnalyticsPeriodWindow;
  language: string;
};

export type DashboardManifestCacheMetadata = {
  cache_key: string;
  analytics_context_hash: string;
  ai_context_hash: string;
  preferences_hash: string;
  manifest_version: string;
  widget_registry_version: string;
  generated_at: string;
  expires_at: string | null;
};

export type DashboardManifest = {
  context: DashboardManifestContext;
  generated_at: string;
  manifest_version: string;
  widget_registry_version: string;
  analytics_context_hash: string;
  ai_context_hash: string;
  widgets: DashboardManifestWidget[];
  widget_registry: DashboardWidgetRegistryEntry[];
  layout_policy: DashboardLayoutPolicy;
  data_quality: DashboardManifestDataQuality;
  provider_status: AIProviderStatus | null;
  cache_metadata: DashboardManifestCacheMetadata | null;
  validation_errors: string[];
};

export type DashboardManifestFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  language?: string;
  forceRefresh?: boolean;
  pinnedWidgetIds?: string[];
  hiddenWidgetIds?: string[];
  lockedPositionWidgetIds?: string[];
  lockedSizeWidgetIds?: string[];
  customWidgetIds?: string[];
};

export type DashboardLauncherState = {
  state: Record<string, unknown>;
  custom_widget_ids: string[];
};

export type DashboardBusinessBreakdown = {
  business_id: string;
  name: string;
  external_ref: string | null;
  source_systems: number;
  contacts: number;
  sales: number;
  marketing_activities: number;
  finance_entries: number;
  revenue: string;
  expense: string;
  net_flow: string;
  rank?: number | null;
  change_percent?: string | null;
  direction?: "up" | "down" | "flat" | "none";
  sold_units?: string;
  average_check?: string;
  returns?: string;
  cash_received?: string;
};

export type DashboardRecentSale = {
  sale_id: string;
  sale_number: string;
  business_id: string;
  business_name: string;
  contact_name: string | null;
  external_ref: string | null;
  amount: string;
  currency: string;
  stage: string;
  sale_at: string;
  items_count: number;
  products_count: number;
};

export type DashboardTopProduct = {
  product_id: string;
  business_id: string;
  business_name: string;
  name: string;
  category: string | null;
  sku: string | null;
  unit: string | null;
  sold_quantity: string;
  sold_amount: string;
  stock_quantity: string;
  last_sold_at: string | null;
  share?: string | null;
  change_percent?: string | null;
  direction?: "up" | "down" | "flat" | "none";
  no_sales_days?: number | null;
  stock_days?: string | null;
  status?: string | null;
  details_href?: string | null;
  data_status?: "available" | "partial" | "unavailable" | "syncing" | "error";
};

export type DashboardInventoryCard = {
  warehouse_name: string;
  product_name: string;
  business_id: string;
  business_name: string;
  quantity: string;
  balance_at: string;
  average_daily_sales?: string | null;
  days_of_stock?: string | null;
  risk_level?: string | null;
  last_sold_at?: string | null;
  details_href?: string | null;
  data_status?: "available" | "partial" | "unavailable" | "syncing" | "error";
};

export type DashboardPaymentCard = {
  payment_id: string;
  business_id: string;
  business_name: string;
  sale_number: string | null;
  amount: string;
  currency: string;
  paid_at: string;
  method: string | null;
  details_href?: string | null;
  data_status?: "available" | "partial" | "unavailable" | "syncing" | "error";
};

export type SmartUpAccessPayload = {
  base_url: string;
  username: string;
  password: string;
  timeout_seconds?: number;
  migration_mode?: SmartUpMigrationMode;
};

export type SmartUpMigrationMode =
  | "full_backfill"
  | "weekly_reconciliation"
  | "one_day_check";

export type SmartUpConnectionCheckResponse = {
  connected: boolean;
  code: string | null;
  message: string;
  upstream_status: number | null;
  upstream_response: string;
  requested_url: string;
  organization_id: string | null;
  organization_name: string | null;
  company_id: string | null;
  filial_id: string | null;
  project_code: string | null;
  ok?: boolean;
  status?: string;
  latency_ms?: number | null;
};

export type SmartUpOrganization = {
  id: string;
  integration_id: string;
  name: string;
  company_id: string;
  filial_id: string;
  project_code: string;
  is_active: boolean;
  sort_order: number;
  last_sync_at: string | null;
  metadata: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type SmartUpOrganizationListResponse = {
  items: SmartUpOrganization[];
};

export type NotificationTab = "Transactions" | "Payouts" | "Invoices" | "System" | "AI Alerts";

export type NotificationTone = "ai" | "success" | "danger" | "info";

export type NotificationItem = {
  id: string;
  title: string;
  message: string;
  time: string;
  tag: NotificationTab;
  tone: NotificationTone;
  unread: boolean;
  read: boolean;
  actionLabel: string;
  detailsHref: string;
};

export type NotificationFeedResponse = {
  generated_at: string;
  unread_count: number;
  total_count: number;
  items: NotificationItem[];
};

type NotificationItemApi = {
  id: string;
  title: string;
  message: string;
  time: string;
  tag: NotificationTab;
  tone: NotificationTone;
  unread: boolean;
  read: boolean;
  action_label: string;
  details_href: string;
};

type NotificationFeedResponseApi = {
  generated_at: string;
  unread_count: number;
  total_count: number;
  items: NotificationItemApi[];
};

export type NotificationMutationResponse = {
  unread_count: number;
  total_count: number;
};

export type SmartUpMigrationStatus = "pending" | "running" | "completed" | "failed";

export type SmartUpOrganizationConnectionState = {
  organization_id: string;
  organization_name: string;
  status: "not_configured" | "checking" | "connected" | "retry_wait" | "error";
  sync_available: boolean;
  code: string | null;
  message: string | null;
  last_checked_at: string | null;
  last_success_at: string | null;
};

export type SmartUpLiveSyncStatus = {
  enabled: boolean;
  status:
    | "not_configured"
    | "initial_sync_required"
    | "initial_sync_running"
    | "ready"
    | "live_sync_running"
    | "retry_wait"
    | "error"
    | "idle"
    | "running"
    | "success"
    | "warning";
  last_started_at: string | null;
  last_completed_at: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
  organizations_processed: number;
  raw_records: number;
  core_records: number;
  canonical_updated: boolean;
  errors_count: number;
  skipped_due_to_running: boolean;
  last_mode: SmartUpMigrationMode | null;
  message: string | null;
  organization_connections: SmartUpOrganizationConnectionState[];
};

export type SmartUpMigrationJobResponse = {
  job_id: string;
  status: SmartUpMigrationStatus;
  message: string;
  migration_mode: SmartUpMigrationMode;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress_organizations: number;
  total_organizations: number;
  current_organization_id: string | null;
  current_organization_name: string | null;
  current_entity_type: string | null;
  current_entity_label: string | null;
  current_phase: string | null;
  result: SmartUpMigrationAllResponse | null;
  error: string | null;
};

export type SmartUpResetResponse = {
  status: "completed";
  message: string;
  preserved_organizations: number;
  cleared_total: number;
  cleared_tables: Record<string, number>;
};

export type SmartUpMigrationRun = {
  run_id: string;
  organization_id: string;
  entity_type: string;
  started_at: string;
  completed_at: string | null;
  status: SmartUpMigrationStatus;
  imported_count: number;
  updated_count: number;
  skipped_count: number;
  failed_count: number;
  error_message: string | null;
  metadata: Record<string, unknown>;
};

export type SmartUpMigrationOrganizationResult = {
  organization_id: string;
  name: string;
  filial_id: string;
  company_id?: string | null;
  project_code?: string | null;
  summary: SmartUpMigrationSummary;
  counters: Record<string, number>;
  runs: SmartUpMigrationRun[];
};

export type SmartUpMigrationSummary = {
  organizations: number;
  businesses: number;
  source_systems: number;
  contacts: number;
  sales: number;
  marketing_activities: number;
  finance_entries: number;
  records: number;
  batches: number;
  errors: number;
};

export type SmartUpBatchImportError = {
  organization_id: string;
  organization_name: string;
  business_id: string;
  batch_id: string;
  batch_name: string;
  batch_status: string;
  source_endpoint: string | null;
  requested_url: string | null;
  payload: Record<string, unknown> | null;
  entity_type: string | null;
  error_code: string;
  error_message: string;
};

export type SmartUpMigrationAllResponse = {
  status: "completed" | "completed_with_errors";
  message: string;
  organizations_count: number;
  organizations: SmartUpMigrationOrganizationResult[];
  runs: SmartUpMigrationRun[];
  summary: SmartUpMigrationSummary;
  counters: Record<string, number>;
  batch_errors: SmartUpBatchImportError[];
  warnings: string[];
  history_start: string;
  history_end: string;
};

export type SmartUpCompletenessGap = {
  period_start: string;
  period_end: string;
};

export type SmartUpCompletenessItem = {
  organization_id: string;
  organization_name: string;
  entity_type: string;
  migration_mode: SmartUpMigrationMode | null;
  batch_count: number;
  completed_batches: number;
  failed_batches: number;
  raw_records: number;
  core_records: number;
  first_period_start: string | null;
  last_period_end: string | null;
  missing_intervals: SmartUpCompletenessGap[];
  status: "empty" | "complete" | "partial" | "failed";
};

export type SmartUpCompletenessReport = {
  total_organizations: number;
  total_entities: number;
  completed_entities: number;
  partial_entities: number;
  failed_entities: number;
  raw_records: number;
  core_records: number;
  items: SmartUpCompletenessItem[];
};

export type SmartUpMigrationLaunchPayload = SmartUpAccessPayload & {
  history_start?: string | null;
  history_end?: string | null;
};

export type SmartUpMigrationCompletenessFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  entityType?: string | null;
  migrationMode?: SmartUpMigrationMode | null;
};

const SMARTUP_ORGANIZATIONS_CACHE_KEY = "ai-business-os:smartup-organizations:v1";

let smartUpOrganizationsCache: SmartUpOrganization[] | null = null;
let smartUpOrganizationsPromise: Promise<SmartUpOrganization[]> | null = null;

function readStoredSmartUpOrganizations(): SmartUpOrganization[] | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(SMARTUP_ORGANIZATIONS_CACHE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as SmartUpOrganization[]) : null;
  } catch {
    return null;
  }
}

function storeSmartUpOrganizations(items: SmartUpOrganization[]) {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.setItem(SMARTUP_ORGANIZATIONS_CACHE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage failures. The in-memory cache still prevents reload flashes.
  }
}

function hydrateSmartUpOrganizationsCache() {
  if (smartUpOrganizationsCache) {
    return smartUpOrganizationsCache;
  }

  smartUpOrganizationsCache = readStoredSmartUpOrganizations();
  return smartUpOrganizationsCache;
}

export function getCachedSmartUpOrganizations(): SmartUpOrganization[] | null {
  return hydrateSmartUpOrganizationsCache();
}

export function prefetchSmartUpOrganizations(): Promise<SmartUpOrganization[]> {
  return getSmartUpOrganizations();
}

export async function getSmartUpOrganizations(
  options: { forceRefresh?: boolean } = {},
): Promise<SmartUpOrganization[]> {
  const cachedOrganizations = hydrateSmartUpOrganizationsCache();

  if (!options.forceRefresh && cachedOrganizations) {
    return cachedOrganizations;
  }

  if (!options.forceRefresh && smartUpOrganizationsPromise) {
    return smartUpOrganizationsPromise;
  }

  const pendingRequest = requestJson<SmartUpOrganizationListResponse>("/api/v1/smartup/organizations", {}, 45_000)
    .then((response) => {
      smartUpOrganizationsCache = response.items;
      storeSmartUpOrganizations(response.items);
      return response.items;
    });

  smartUpOrganizationsPromise = pendingRequest;

  try {
    return await pendingRequest;
  } finally {
    if (smartUpOrganizationsPromise === pendingRequest) {
      smartUpOrganizationsPromise = null;
    }
  }
}

export async function testSmartUpOrganizationConnection(
  organizationId: string,
  payload: SmartUpAccessPayload,
): Promise<SmartUpConnectionCheckResponse> {
  return requestJson<SmartUpConnectionCheckResponse>(
    `/api/v1/smartup/organizations/${organizationId}/test`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    30_000,
  );
}

export async function startSmartUpMigrationJob(
  payload: SmartUpMigrationLaunchPayload,
): Promise<SmartUpMigrationJobResponse> {
  return requestJson<SmartUpMigrationJobResponse>("/api/v1/smartup/migrate-all", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSmartUpMigrationJob(
  jobId: string,
): Promise<SmartUpMigrationJobResponse> {
  return requestJson<SmartUpMigrationJobResponse>(`/api/v1/smartup/migration-jobs/${jobId}`);
}

export async function getSmartUpLiveSyncStatus(): Promise<SmartUpLiveSyncStatus> {
  return requestJson<SmartUpLiveSyncStatus>("/api/v1/smartup/live-sync/status");
}

export type SystemUpdateStatus = {
  current_version: string | null;
  latest_version: string | null;
  update_available: boolean;
  status: "ready";
  last_successful_update_at: string | null;
};

export type SystemUpdateJob = {
  job_id: string;
  status: "running" | "success" | "failed" | "rollback";
  stage: string;
  message: string;
  current_version: string | null;
  target_version: string | null;
  previous_commit: string | null;
  target_commit: string | null;
  error: string | null;
};

export async function getSystemUpdateStatus(): Promise<SystemUpdateStatus> {
  return requestJson<SystemUpdateStatus>("/api/v1/system/update/status", {}, 35_000);
}

export async function installSystemUpdate(): Promise<SystemUpdateJob> {
  return requestJson<SystemUpdateJob>("/api/v1/system/update/install", { method: "POST" }, 10_000);
}

export async function getSystemUpdateJob(jobId: string): Promise<SystemUpdateJob> {
  return requestJson<SystemUpdateJob>(`/api/v1/system/update/jobs/${jobId}`, {}, 10_000);
}

export type SmartUpPage = "sales" | "visits" | "products" | "customers" | "inventory" | "finance";

export async function startSmartUpPageSync(page: SmartUpPage): Promise<SmartUpMigrationJobResponse> {
  return requestJson<SmartUpMigrationJobResponse>("/api/v1/smartup/sync-page", {
    method: "POST",
    body: JSON.stringify({ page }),
  }, 10_000);
}

export async function migrateSmartUpOrganization(
  organizationId: string,
  payload: SmartUpMigrationLaunchPayload,
): Promise<SmartUpMigrationAllResponse> {
  return requestJson<SmartUpMigrationAllResponse>(
    `/api/v1/smartup/organizations/${organizationId}/migrate`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function getSmartUpMigrationCompleteness(
  filters: SmartUpMigrationCompletenessFilters = {},
): Promise<SmartUpCompletenessReport> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.migrationMode) params.set("migration_mode", filters.migrationMode);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<SmartUpCompletenessReport>(`/api/v1/smartup/migration/completeness${suffix}`);
}

export async function resetSmartUpImportedData(): Promise<SmartUpResetResponse> {
  return requestJson<SmartUpResetResponse>("/api/v1/smartup/reset-data", {
    method: "POST",
  }, 180_000);
}

export type SalesWorkspaceSortBy =
  | "business_date"
  | "order_amount"
  | "realised_amount"
  | "sold_units"
  | "customer"
  | "organization"
  | "status";

export type SalesWorkspaceSortOrder = "asc" | "desc";

export type SalesWorkspaceRowKind = "order" | "sale";

export type SalesWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type SalesWorkspaceFiltersMetadata = {
  organizations: SalesWorkspaceFilterOption[];
  statuses: SalesWorkspaceFilterOption[];
  customers: SalesWorkspaceFilterOption[];
  sales_reps: SalesWorkspaceFilterOption[];
  working_zones: SalesWorkspaceFilterOption[];
  data_quality: SalesWorkspaceFilterOption[];
};

export type SalesWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type SalesWorkspaceSummary = {
  revenue: AnalyticsMetricValue;
  orders: AnalyticsMetricValue;
  realised_sales: AnalyticsMetricValue;
  sold_units: AnalyticsMetricValue;
  average_order: AnalyticsMetricValue;
  unique_customers: AnalyticsMetricValue;
  payments_received: AnalyticsMetricValue;
  return_value: AnalyticsMetricValue;
};

export type SalesWorkspaceRow = {
  record_id: string;
  row_kind: SalesWorkspaceRowKind;
  order_id: string | null;
  sale_id: string | null;
  order_external_id: string | null;
  sale_external_id: string | null;
  deal_id: string | null;
  order_number: string | null;
  sale_number: string | null;
  business_date: string | null;
  delivery_date: string | null;
  last_modified_at: string | null;
  organization_id: string;
  organization_name: string;
  customer_id: string | null;
  customer_external_id: string | null;
  customer_code: string | null;
  customer_name: string | null;
  sales_rep_id: string | null;
  sales_rep_name: string | null;
  working_zone_id: string | null;
  working_zone_name: string | null;
  source_status_code: string | null;
  source_status_name: string | null;
  normalized_status: string;
  display_status: string;
  order_amount: string | null;
  realised_amount: string | null;
  return_value: string | null;
  linked_payment_amount: string | null;
  ordered_units: string | null;
  sold_units: string | null;
  returned_units: string | null;
  item_count: number;
  currency_code: string | null;
  realised: boolean;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
};

export type SalesWorkspaceLineItem = {
  line_number: number;
  product_id: string | null;
  product_external_id: string | null;
  product_code: string | null;
  product_name: string | null;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  price_type_code: string | null;
  ordered_quantity: string | null;
  sold_quantity: string | null;
  returned_quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  vat_percent: string | null;
  vat_amount: string | null;
  margin_amount: string | null;
  currency_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type SalesWorkspaceReturnItem = {
  return_id: string;
  return_number: string | null;
  return_at: string | null;
  product_code: string | null;
  product_name: string | null;
  returned_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  reason_code: string | null;
  status: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type SalesWorkspacePaymentItem = {
  payment_id: string;
  payment_number: string | null;
  paid_at: string | null;
  amount: string | null;
  currency_code: string | null;
  normalized_payment_type: string | null;
  allocation_type: string;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type SalesWorkspaceProvenance = {
  source_endpoint: string;
  source_external_id: string;
  source_raw_record_id: string | null;
  request_filial_id: string | null;
  response_filial_id: string | null;
  request_company_id: string | null;
  request_project_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type SalesWorkspaceDetail = {
  record_id: string;
  row: SalesWorkspaceRow;
  items: SalesWorkspaceLineItem[];
  returns: SalesWorkspaceReturnItem[];
  payments: SalesWorkspacePaymentItem[];
  provenance: SalesWorkspaceProvenance;
  limitations: string[];
};

export type SalesWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  summary: SalesWorkspaceSummary;
  filters: SalesWorkspaceFiltersMetadata;
  rows: SalesWorkspaceRow[];
  pagination: SalesWorkspacePagination;
};

export type SalesWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  search?: string | null;
  status?: string[];
  customer?: string[];
  product?: string | null;
  salesRep?: string[];
  workingZone?: string[];
  realised?: boolean | null;
  hasReturns?: boolean | null;
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  amountMin?: string | number | null;
  amountMax?: string | number | null;
  sortBy?: SalesWorkspaceSortBy;
  sortOrder?: SalesWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

export type CustomerWorkspaceSortBy =
  | "customer_name"
  | "revenue"
  | "orders"
  | "sold_units"
  | "average_order"
  | "payments"
  | "returns"
  | "visits"
  | "last_purchase";

export type CustomerWorkspaceSortOrder = "asc" | "desc";

export type CustomerWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type CustomerWorkspaceFiltersMetadata = {
  organizations: CustomerWorkspaceFilterOption[];
  customer_types: CustomerWorkspaceFilterOption[];
  sales_reps: CustomerWorkspaceFilterOption[];
  working_zones: CustomerWorkspaceFilterOption[];
  data_quality: CustomerWorkspaceFilterOption[];
};

export type CustomerWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type CustomerWorkspaceSummary = {
  unique_customers: AnalyticsMetricValue;
  customers_with_sales: AnalyticsMetricValue;
  revenue: AnalyticsMetricValue;
  average_revenue_per_customer: AnalyticsMetricValue;
  payments_received: AnalyticsMetricValue;
  return_value: AnalyticsMetricValue;
  visits: AnalyticsMetricValue;
  active_customers: AnalyticsMetricValue;
};

export type CustomerWorkspaceRow = {
  customer_id: string;
  customer_external_id: string;
  customer_code: string | null;
  customer_name: string;
  organization_ids: string[];
  organization_names: string[];
  customer_type: string | null;
  orders_count: string | null;
  realised_sales_count: string | null;
  revenue: string | null;
  sold_units: string | null;
  average_order_value: string | null;
  payments_received: string | null;
  return_value: string | null;
  visits_count: string | null;
  first_purchase: string | null;
  last_purchase: string | null;
  days_since_last_purchase: string | null;
  products_bought_count: string | null;
  sales_rep_names: string[];
  working_zone_names: string[];
  phone: string | null;
  email: string | null;
  address: string | null;
  group_names: string[];
  segment: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
};

export type CustomerWorkspaceProductRow = {
  product_id: string | null;
  product_code: string | null;
  product_name: string | null;
  sold_units: string | null;
  revenue: string | null;
  orders_count: string | null;
  return_quantity: string | null;
  last_purchase: string | null;
  currency_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type CustomerWorkspaceSaleRow = {
  record_id: string;
  order_id: string | null;
  sale_id: string | null;
  deal_id: string | null;
  order_number: string | null;
  sale_number: string | null;
  organization_id: string;
  organization_name: string;
  business_date: string | null;
  normalized_status: string;
  display_status: string;
  order_amount: string | null;
  realised_amount: string | null;
  sold_units: string | null;
  currency_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type CustomerWorkspacePaymentRow = {
  payment_id: string;
  organization_id: string;
  organization_name: string;
  paid_at: string | null;
  payment_number: string | null;
  amount: string | null;
  currency_code: string | null;
  normalized_payment_type: string | null;
  allocation_type: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type CustomerWorkspaceReturnRow = {
  return_id: string;
  organization_id: string;
  organization_name: string;
  return_number: string | null;
  return_at: string | null;
  amount: string | null;
  returned_quantity: string | null;
  currency_code: string | null;
  status: string | null;
  products: string[];
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type CustomerWorkspaceVisitRow = {
  visit_id: string;
  organization_id: string;
  organization_name: string;
  visit_date: string | null;
  sales_rep_name: string | null;
  working_zone_name: string | null;
  status: string;
  duration_seconds: number | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type CustomerWorkspaceTimelineEvent = {
  event_id: string;
  event_type: string;
  title: string;
  happened_at: string | null;
  organization_name: string | null;
  amount: string | null;
  quantity: string | null;
  currency_code: string | null;
  reference_id: string | null;
  reference_type: string | null;
  drilldown_target: string | null;
  description: string | null;
};

export type CustomerWorkspaceProvenance = {
  canonical_customer_id: string;
  source_endpoint: string;
  source_external_id: string;
  source_raw_record_id: string | null;
  request_filial_id: string | null;
  response_filial_id: string | null;
  request_company_id: string | null;
  request_project_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  reference_sources: string[];
};

export type CustomerWorkspaceDetail = {
  customer_id: string;
  row: CustomerWorkspaceRow;
  overview: CustomerWorkspaceSummary;
  sales: CustomerWorkspaceSaleRow[];
  products: CustomerWorkspaceProductRow[];
  payments: CustomerWorkspacePaymentRow[];
  returns: CustomerWorkspaceReturnRow[];
  visits: CustomerWorkspaceVisitRow[];
  timeline: CustomerWorkspaceTimelineEvent[];
  ai_summary: string | null;
  provenance: CustomerWorkspaceProvenance;
  limitations: string[];
};

export type CustomerWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  summary: CustomerWorkspaceSummary;
  filters: CustomerWorkspaceFiltersMetadata;
  rows: CustomerWorkspaceRow[];
  pagination: CustomerWorkspacePagination;
};

export type CustomerWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  search?: string | null;
  hasSales?: boolean | null;
  hasPayments?: boolean | null;
  hasReturns?: boolean | null;
  hasVisits?: boolean | null;
  customerType?: string[];
  salesRep?: string[];
  workingZone?: string[];
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  revenueMin?: string | number | null;
  revenueMax?: string | number | null;
  sortBy?: CustomerWorkspaceSortBy;
  sortOrder?: CustomerWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

export type VisitsWorkspaceSortBy =
  | "date"
  | "customer"
  | "sales_rep"
  | "working_zone"
  | "status"
  | "organization";

export type VisitsWorkspaceSortOrder = "asc" | "desc";

export type VisitsWorkspaceTab =
  | "visits"
  | "sales_reps"
  | "working_zones"
  | "capabilities";

export type VisitsWorkspaceCapabilityStatus =
  | "AVAILABLE"
  | "PARTIAL"
  | "NO_DATA"
  | "NOT_AVAILABLE"
  | "NO_DATA_IN_CURRENT_RAW";

export type VisitsWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type VisitsWorkspaceFiltersMetadata = {
  organizations: VisitsWorkspaceFilterOption[];
  customers: VisitsWorkspaceFilterOption[];
  sales_reps: VisitsWorkspaceFilterOption[];
  working_zones: VisitsWorkspaceFilterOption[];
  statuses: VisitsWorkspaceFilterOption[];
  planned: VisitsWorkspaceFilterOption[];
  data_quality: VisitsWorkspaceFilterOption[];
};

export type VisitsWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type VisitsWorkspaceSummary = {
  visits: AnalyticsMetricValue;
  unique_customers: AnalyticsMetricValue;
  sales_reps: AnalyticsMetricValue;
  working_zones: AnalyticsMetricValue;
  planned_visits: AnalyticsMetricValue;
  completed_visits: AnalyticsMetricValue;
  average_duration: AnalyticsMetricValue;
  visit_conversion: AnalyticsMetricValue;
};

export type VisitsWorkspaceTabStatus = {
  tab: VisitsWorkspaceTab;
  label: string;
  count: number;
  status: VisitsWorkspaceCapabilityStatus;
  note: string | null;
};

export type VisitsWorkspaceVisitRow = {
  visit_id: string;
  source_visit_id: string | null;
  source_external_id: string;
  business_date: string | null;
  organization_id: string;
  organization_name: string;
  customer_id: string | null;
  customer_external_id: string | null;
  customer_code: string | null;
  customer_name: string | null;
  sales_rep_id: string | null;
  sales_rep_name: string | null;
  working_zone_id: string | null;
  working_zone_name: string | null;
  source_status_code: string | null;
  normalized_status: string;
  display_status: string;
  is_planned: boolean | null;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  has_comments: boolean;
  has_media: boolean;
  has_visit_stock: boolean;
  has_quiz_answers: boolean;
  has_equipment: boolean;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
};

export type VisitsWorkspaceSalesRepRow = {
  sales_rep_id: string;
  sales_rep_key: string;
  sales_rep_name: string;
  organization_ids: string[];
  organization_names: string[];
  visits: AnalyticsMetricValue;
  unique_customers: AnalyticsMetricValue;
  working_zones: AnalyticsMetricValue;
  completed_visits: AnalyticsMetricValue;
  planned_visits: AnalyticsMetricValue;
  visit_conversion: AnalyticsMetricValue;
  data_status: AnalyticsDataStatus;
};

export type VisitsWorkspaceWorkingZoneRow = {
  working_zone_id: string;
  working_zone_key: string;
  working_zone_name: string;
  organization_ids: string[];
  organization_names: string[];
  visits: AnalyticsMetricValue;
  unique_customers: AnalyticsMetricValue;
  sales_reps: AnalyticsMetricValue;
  data_status: AnalyticsDataStatus;
};

export type VisitsWorkspaceCapabilityItem = {
  key: string;
  label: string;
  status: VisitsWorkspaceCapabilityStatus;
  message: string;
  count: number | null;
};

export type VisitsWorkspaceRows = {
  visits: VisitsWorkspaceVisitRow[];
  sales_reps: VisitsWorkspaceSalesRepRow[];
  working_zones: VisitsWorkspaceWorkingZoneRow[];
  capabilities: VisitsWorkspaceCapabilityItem[];
};

export type VisitsWorkspaceProvenance = {
  source_endpoint: string;
  source_external_id: string;
  source_raw_record_id: string | null;
  request_filial_id: string | null;
  response_filial_id: string | null;
  request_company_id: string | null;
  request_project_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceNestedStockRow = {
  line_number: number;
  product_id: string | null;
  product_external_id: string | null;
  product_code: string | null;
  product_name: string | null;
  quantity: string | null;
  expiry_date: string | null;
  card_code: string | null;
  serial_number: string | null;
  inventory_kind: string | null;
  unavailable_reason: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceNestedQuizRow = {
  line_number: number;
  quiz_external_id: string | null;
  quiz_name: string | null;
  question_external_id: string | null;
  question_text: string | null;
  answer_value: string | null;
  answer_type: string | null;
  photo_sha: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceNestedEquipmentRow = {
  line_number: number;
  equipment_external_id: string | null;
  equipment_code: string | null;
  equipment_name: string | null;
  serial_number: string | null;
  status_code: string | null;
  note: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceNestedCommentRow = {
  line_number: number;
  comment_text: string | null;
  comment_type: string | null;
  created_by_external_id: string | null;
  created_at_source: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceNestedMediaRow = {
  media_id: string | null;
  media_type: string | null;
  source_sha: string | null;
  source_reference: string | null;
  download_status: string;
  local_path: string | null;
  mime_type: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type VisitsWorkspaceRelatedCustomer = {
  customer_id: string | null;
  customer_external_id: string | null;
  customer_code: string | null;
  customer_name: string | null;
  detail_href: string | null;
};

export type VisitsWorkspaceRelatedSalesRep = {
  sales_rep_id: string | null;
  sales_rep_external_id: string | null;
  sales_rep_code: string | null;
  sales_rep_name: string | null;
};

export type VisitsWorkspaceRelatedWorkingZone = {
  working_zone_id: string | null;
  working_zone_external_id: string | null;
  working_zone_code: string | null;
  working_zone_name: string | null;
};

export type VisitsWorkspaceDetail = {
  visit_id: string;
  row: VisitsWorkspaceVisitRow;
  customer: VisitsWorkspaceRelatedCustomer;
  sales_rep: VisitsWorkspaceRelatedSalesRep;
  working_zone: VisitsWorkspaceRelatedWorkingZone;
  visit_stocks: VisitsWorkspaceNestedStockRow[];
  quiz_answers: VisitsWorkspaceNestedQuizRow[];
  equipments: VisitsWorkspaceNestedEquipmentRow[];
  comments: VisitsWorkspaceNestedCommentRow[];
  media_assets: VisitsWorkspaceNestedMediaRow[];
  related_sales_status: AnalyticsDataStatus;
  provenance: VisitsWorkspaceProvenance;
  limitations: string[];
};

export type VisitsWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  active_tab: VisitsWorkspaceTab;
  summary: VisitsWorkspaceSummary;
  filters: VisitsWorkspaceFiltersMetadata;
  tabs: VisitsWorkspaceTabStatus[];
  rows: VisitsWorkspaceRows;
  pagination: VisitsWorkspacePagination;
  data_quality: AnalyticsDataQualityReport;
};

export type VisitsWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  tab?: VisitsWorkspaceTab;
  search?: string | null;
  customer?: string[];
  salesRep?: string[];
  workingZone?: string[];
  status?: string[];
  planned?: string[];
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  sortBy?: VisitsWorkspaceSortBy;
  sortOrder?: VisitsWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

export type ProductWorkspaceSortBy =
  | "product_name"
  | "revenue"
  | "sold_units"
  | "orders"
  | "customers"
  | "current_stock"
  | "last_sale"
  | "return_quantity";

export type ProductWorkspaceSortOrder = "asc" | "desc";

export type ProductWorkspaceStockStatus =
  | "IN_STOCK"
  | "LOW_STOCK"
  | "OUT_OF_STOCK"
  | "OVERSTOCK";

export type ProductWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type ProductWorkspaceFiltersMetadata = {
  organizations: ProductWorkspaceFilterOption[];
  categories: ProductWorkspaceFilterOption[];
  stock_statuses: ProductWorkspaceFilterOption[];
  data_quality: ProductWorkspaceFilterOption[];
};

export type ProductWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type ProductWorkspaceSummary = {
  products: AnalyticsMetricValue;
  products_sold: AnalyticsMetricValue;
  sold_units: AnalyticsMetricValue;
  revenue: AnalyticsMetricValue;
  average_selling_price: AnalyticsMetricValue;
  current_stock: AnalyticsMetricValue;
  out_of_stock: AnalyticsMetricValue;
  low_stock: AnalyticsMetricValue;
  overstock: AnalyticsMetricValue;
  return_quantity: AnalyticsMetricValue;
  return_value: AnalyticsMetricValue;
};

export type ProductWorkspaceRow = {
  product_id: string;
  product_external_id: string;
  product_code: string | null;
  product_name: string;
  category_id: string | null;
  category_name: string | null;
  organization_ids: string[];
  organization_names: string[];
  measure_code: string | null;
  producer_code: string | null;
  article_code: string | null;
  barcodes: string[];
  sold_units: string | null;
  revenue: string | null;
  orders_count: string | null;
  customers_count: string | null;
  average_selling_price: string | null;
  current_stock: string | null;
  last_sale: string | null;
  first_sale: string | null;
  return_quantity: string | null;
  return_value: string | null;
  stock_status: ProductWorkspaceStockStatus | null;
  stock_status_reason: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
};

export type ProductWorkspaceSaleRow = {
  sale_item_id: string;
  sale_id: string | null;
  order_id: string | null;
  business_date: string | null;
  organization_id: string;
  organization_name: string;
  order_number: string | null;
  sale_number: string | null;
  deal_id: string | null;
  customer_id: string | null;
  customer_name: string | null;
  sold_quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  currency_code: string | null;
  display_status: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspaceOrganizationRow = {
  organization_id: string;
  organization_name: string;
  revenue: string | null;
  sold_units: string | null;
  orders_count: string | null;
  customers_count: string | null;
  current_stock: string | null;
  last_sale: string | null;
  stock_status: ProductWorkspaceStockStatus | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspaceCustomerRow = {
  customer_id: string;
  customer_name: string;
  organization_id: string;
  organization_name: string;
  sold_units: string | null;
  revenue: string | null;
  orders_count: string | null;
  last_purchase: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspaceInventoryRow = {
  inventory_balance_id: string;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  snapshot_date: string | null;
  quantity: string | null;
  available_quantity: string | null;
  reserved_quantity: string | null;
  input_price: string | null;
  valuation_amount: string | null;
  currency_code: string | null;
  batch_number: string | null;
  card_code: string | null;
  serial_number: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspacePriceRow = {
  price_id: string | null;
  source_type: string;
  organization_id: string;
  organization_name: string;
  price_type_code: string | null;
  price_type_name: string | null;
  price: string | null;
  currency_code: string | null;
  effective_date: string | null;
  note: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspaceReturnRow = {
  return_item_id: string;
  return_id: string;
  organization_id: string;
  organization_name: string;
  return_number: string | null;
  return_at: string | null;
  customer_id: string | null;
  customer_name: string | null;
  returned_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  status: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type ProductWorkspaceTimelineEvent = {
  event_id: string;
  event_type: string;
  title: string;
  happened_at: string | null;
  organization_name: string | null;
  amount: string | null;
  quantity: string | null;
  currency_code: string | null;
  reference_id: string | null;
  reference_type: string | null;
  drilldown_target: string | null;
  description: string | null;
};

export type ProductWorkspaceProvenance = {
  canonical_product_id: string;
  source_endpoint: string;
  source_external_id: string;
  source_raw_record_id: string | null;
  request_filial_id: string | null;
  response_filial_id: string | null;
  request_company_id: string | null;
  request_project_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  reference_sources: string[];
};

export type ProductWorkspaceDetail = {
  product_id: string;
  row: ProductWorkspaceRow;
  overview: ProductWorkspaceSummary;
  sales: ProductWorkspaceSaleRow[];
  organizations: ProductWorkspaceOrganizationRow[];
  customers: ProductWorkspaceCustomerRow[];
  inventory: ProductWorkspaceInventoryRow[];
  prices: ProductWorkspacePriceRow[];
  returns: ProductWorkspaceReturnRow[];
  timeline: ProductWorkspaceTimelineEvent[];
  ai_summary: string | null;
  provenance: ProductWorkspaceProvenance;
  limitations: string[];
};

export type ProductWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  summary: ProductWorkspaceSummary;
  filters: ProductWorkspaceFiltersMetadata;
  rows: ProductWorkspaceRow[];
  pagination: ProductWorkspacePagination;
};

export type ProductWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  search?: string | null;
  categoryIds?: string[];
  stockStatus?: ProductWorkspaceStockStatus[];
  hasSales?: boolean | null;
  hasReturns?: boolean | null;
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  revenueMin?: string | number | null;
  revenueMax?: string | number | null;
  soldUnitsMin?: string | number | null;
  soldUnitsMax?: string | number | null;
  sortBy?: ProductWorkspaceSortBy;
  sortOrder?: ProductWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

export type InventoryWorkspaceView =
  | "current_stock"
  | "warehouses"
  | "purchases"
  | "receipts"
  | "writeoffs"
  | "movements"
  | "stocktaking"
  | "supplier_returns";

export type InventoryWorkspaceSortBy =
  | "product_name"
  | "warehouse"
  | "organization"
  | "quantity"
  | "snapshot_date"
  | "stock_status"
  | "document_date"
  | "amount";

export type InventoryWorkspaceSortOrder = "asc" | "desc";

export type InventoryWorkspaceStockStatus =
  | "IN_STOCK"
  | "LOW_STOCK"
  | "OUT_OF_STOCK"
  | "OVERSTOCK"
  | "STOCKOUT_RISK"
  | "NEGATIVE_STOCK";

export type InventoryWorkspaceCapabilityStatus =
  | "AVAILABLE"
  | "NO_DATA"
  | "NO_VERIFIED_DATA"
  | "NOT_IMPORTED"
  | "SOURCE_NOT_AVAILABLE"
  | "PERMISSION_RESTRICTED"
  | "UNRESOLVED";

export type InventoryWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type InventoryWorkspaceFiltersMetadata = {
  organizations: InventoryWorkspaceFilterOption[];
  warehouses: InventoryWorkspaceFilterOption[];
  categories: InventoryWorkspaceFilterOption[];
  products: InventoryWorkspaceFilterOption[];
  stock_statuses: InventoryWorkspaceFilterOption[];
  data_quality: InventoryWorkspaceFilterOption[];
};

export type InventoryWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type InventoryWorkspaceSummary = {
  current_stock_quantity: AnalyticsMetricValue;
  products_in_stock: AnalyticsMetricValue;
  warehouses: AnalyticsMetricValue;
  zero_stock_products: AnalyticsMetricValue;
  negative_stock_products: AnalyticsMetricValue;
  low_stock_signals: AnalyticsMetricValue;
  overstock_signals: AnalyticsMetricValue;
  inventory_value: AnalyticsMetricValue;
};

export type InventoryWorkspaceTabStatus = {
  view: InventoryWorkspaceView;
  label: string;
  count: number;
  status: InventoryWorkspaceCapabilityStatus;
  note: string | null;
};

export type InventoryWorkspaceCurrentStockRow = {
  inventory_balance_id: string;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  product_id: string | null;
  product_code: string | null;
  product_name: string;
  category_id: string | null;
  category_name: string | null;
  quantity: string | null;
  available_quantity: string | null;
  reserved_quantity: string | null;
  snapshot_date: string | null;
  valuation_amount: string | null;
  currency_code: string | null;
  sales_velocity_30d: string | null;
  days_of_stock: string | null;
  stock_status: InventoryWorkspaceStockStatus;
  stock_status_reason: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
  batch_number: string | null;
  expiry_date: string | null;
  inventory_kind: string | null;
};

export type InventoryWorkspaceWarehouseRow = {
  warehouse_key: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  organization_id: string;
  organization_name: string;
  products_count: number;
  current_quantity: string | null;
  last_snapshot: string | null;
  low_stock_count: number;
  out_of_stock_count: number;
  overstock_count: number;
  negative_stock_count: number;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type InventoryWorkspacePurchaseRow = {
  purchase_id: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  supplier_code: string | null;
  supplier_external_id: string | null;
  amount: string | null;
  currency_code: string | null;
  status: string | null;
  items_count: number;
  total_quantity: string | null;
  product_linkage_coverage: string | null;
  warehouse_linkage_coverage: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  quality_note: string | null;
};

export type InventoryWorkspaceReceiptRow = {
  receipt_id: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  supplier_code: string | null;
  supplier_external_id: string | null;
  linked_purchase_external_id: string | null;
  items_count: number;
  total_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  quality_note: string | null;
};

export type InventoryWorkspaceWriteoffRow = {
  writeoff_id: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  reason_code: string | null;
  items_count: number;
  total_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  status: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type InventoryWorkspaceMovementRow = {
  movement_id: string;
  movement_type: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  source_organization_name: string | null;
  source_warehouse_code: string | null;
  source_warehouse_name: string | null;
  destination_organization_name: string | null;
  destination_warehouse_code: string | null;
  destination_warehouse_name: string | null;
  total_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  direction: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type InventoryWorkspaceStocktakingRow = {
  stocktaking_id: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  items_count: number;
  total_quantity: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type InventoryWorkspaceSupplierReturnRow = {
  supplier_return_id: string;
  source_external_id: string;
  document_number: string | null;
  document_date: string | null;
  organization_id: string;
  organization_name: string;
  warehouse_id: string | null;
  warehouse_code: string | null;
  warehouse_name: string | null;
  supplier_code: string | null;
  supplier_external_id: string | null;
  reason_code: string | null;
  items_count: number;
  total_quantity: string | null;
  amount: string | null;
  currency_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type InventoryWorkspaceRows = {
  current_stock: InventoryWorkspaceCurrentStockRow[];
  warehouses: InventoryWorkspaceWarehouseRow[];
  purchases: InventoryWorkspacePurchaseRow[];
  receipts: InventoryWorkspaceReceiptRow[];
  writeoffs: InventoryWorkspaceWriteoffRow[];
  movements: InventoryWorkspaceMovementRow[];
  stocktaking: InventoryWorkspaceStocktakingRow[];
  supplier_returns: InventoryWorkspaceSupplierReturnRow[];
};

export type InventoryWorkspaceCurrentStockDetail = {
  row: InventoryWorkspaceCurrentStockRow;
  recent_snapshots: InventoryWorkspaceCurrentStockRow[];
  recent_receipts: InventoryWorkspaceReceiptRow[];
  recent_writeoffs: InventoryWorkspaceWriteoffRow[];
  recent_movements: InventoryWorkspaceMovementRow[];
  limitations: string[];
};

export type InventoryWorkspaceWarehouseDetail = {
  row: InventoryWorkspaceWarehouseRow;
  current_stock: InventoryWorkspaceCurrentStockRow[];
  purchases: InventoryWorkspacePurchaseRow[];
  receipts: InventoryWorkspaceReceiptRow[];
  writeoffs: InventoryWorkspaceWriteoffRow[];
  movements: InventoryWorkspaceMovementRow[];
  stocktaking: InventoryWorkspaceStocktakingRow[];
  supplier_returns: InventoryWorkspaceSupplierReturnRow[];
  limitations: string[];
};

export type InventoryWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  active_view: InventoryWorkspaceView;
  summary: InventoryWorkspaceSummary;
  tabs: InventoryWorkspaceTabStatus[];
  filters: InventoryWorkspaceFiltersMetadata;
  pagination: InventoryWorkspacePagination;
  rows: InventoryWorkspaceRows;
};

export type InventoryWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  view?: InventoryWorkspaceView;
  search?: string | null;
  warehouseId?: string[];
  productId?: string[];
  categoryId?: string[];
  stockStatus?: InventoryWorkspaceStockStatus[];
  hasStock?: boolean | null;
  zeroStock?: boolean | null;
  negativeStock?: boolean | null;
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  sortBy?: InventoryWorkspaceSortBy;
  sortOrder?: InventoryWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

export type FinanceWorkspaceView =
  | "overview"
  | "payments"
  | "cash_operations"
  | "bank_operations"
  | "financial_operations"
  | "returns"
  | "accounts";

export type FinanceWorkspaceSortBy =
  | "date"
  | "amount"
  | "organization"
  | "operation_type"
  | "direction"
  | "customer"
  | "account";

export type FinanceWorkspaceSortOrder = "asc" | "desc";

export type FinanceWorkspaceCapabilityStatus =
  | "AVAILABLE"
  | "PARTIAL"
  | "NO_DATA"
  | "NO_VERIFIED_DATA"
  | "NOT_AVAILABLE"
  | "UNRESOLVED";

export type FinanceWorkspaceDirection =
  | "INFLOW"
  | "OUTFLOW"
  | "TRANSFER"
  | "UNKNOWN";

export type FinanceWorkspaceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type FinanceWorkspaceFiltersMetadata = {
  organizations: FinanceWorkspaceFilterOption[];
  directions: FinanceWorkspaceFilterOption[];
  operation_types: FinanceWorkspaceFilterOption[];
  payment_types: FinanceWorkspaceFilterOption[];
  counterparties: FinanceWorkspaceFilterOption[];
  accounts: FinanceWorkspaceFilterOption[];
  currencies: FinanceWorkspaceFilterOption[];
  data_quality: FinanceWorkspaceFilterOption[];
};

export type FinanceWorkspacePagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

export type FinanceWorkspaceSummary = {
  payments_received: AnalyticsMetricValue;
  verified_cash_in: AnalyticsMetricValue;
  verified_cash_out: AnalyticsMetricValue;
  net_cash_flow: AnalyticsMetricValue;
  customer_return_value: AnalyticsMetricValue;
  financial_operations_count: AnalyticsMetricValue;
};

export type FinanceWorkspaceCoverageItem = {
  key: string;
  label: string;
  status: FinanceWorkspaceCapabilityStatus;
  message: string;
  affected_domains: string[];
};

export type FinanceWorkspaceTabStatus = {
  view: FinanceWorkspaceView;
  label: string;
  count: number;
  status: FinanceWorkspaceCapabilityStatus;
  note: string | null;
};

export type FinanceWorkspaceProvenance = {
  source_endpoint: string;
  source_external_id: string;
  source_raw_record_id: string | null;
  request_filial_id: string | null;
  response_filial_id: string | null;
  request_company_id: string | null;
  request_project_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
};

export type FinanceWorkspaceOverviewRow = {
  organization_id: string;
  organization_name: string;
  payments_received: string | null;
  verified_cash_in: string | null;
  verified_cash_out: string | null;
  customer_return_value: string | null;
  financial_operations_count: number;
  payments_count: number;
  returns_count: number;
  purchases_count: number;
  writeoffs_count: number;
  data_status: AnalyticsDataStatus;
};

export type FinanceWorkspacePaymentRow = {
  payment_id: string;
  source_external_id: string;
  payment_number: string | null;
  paid_at: string | null;
  organization_id: string;
  organization_name: string;
  customer_id: string | null;
  customer_name: string | null;
  amount: string | null;
  currency_code: string | null;
  payment_type: string | null;
  cashbox_or_account: string | null;
  purpose: string | null;
  allocation_status: string;
  linked_order_id: string | null;
  linked_order_external_id: string | null;
  linked_sale_id: string | null;
  linked_sale_external_id: string | null;
  linked_order_number: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
  provenance: FinanceWorkspaceProvenance;
};

export type FinanceWorkspaceOperationRow = {
  operation_id: string;
  source_external_id: string;
  source_type: string;
  source_label: string;
  operation_number: string | null;
  operation_at: string | null;
  organization_id: string;
  organization_name: string;
  operation_type: string | null;
  direction: FinanceWorkspaceDirection;
  account_id: string | null;
  account_label: string | null;
  counterparty_type: string | null;
  counterparty_id: string | null;
  counterparty_name: string | null;
  purpose: string | null;
  amount: string | null;
  currency_code: string | null;
  posted: string | null;
  is_internal_transfer: boolean;
  overlaps_customer_payment: boolean;
  overlap_note: string | null;
  source_document_type: string | null;
  source_document_external_id: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
  provenance: FinanceWorkspaceProvenance;
};

export type FinanceWorkspaceReturnRow = {
  customer_return_id: string;
  source_external_id: string;
  return_number: string | null;
  return_at: string | null;
  organization_id: string;
  organization_name: string;
  customer_id: string | null;
  customer_name: string | null;
  value: string | null;
  currency_code: string | null;
  returned_units: string | null;
  products_count: number;
  reason_code: string | null;
  status: string | null;
  cash_refund_status: string;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
  provenance: FinanceWorkspaceProvenance;
};

export type FinanceWorkspaceAccountRow = {
  account_id: string;
  source_external_id: string;
  organization_id: string;
  organization_name: string;
  account_code: string;
  account_name: string | null;
  account_type: string | null;
  currency_code: string | null;
  bank_name: string | null;
  bank_account_code: string | null;
  cashbox_code: string | null;
  data_quality_status: "verified" | "partial" | "unresolved" | "unsafe";
  data_status: AnalyticsDataStatus;
  provenance: FinanceWorkspaceProvenance;
};

export type FinanceWorkspaceRows = {
  overview: FinanceWorkspaceOverviewRow[];
  payments: FinanceWorkspacePaymentRow[];
  cash_operations: FinanceWorkspaceOperationRow[];
  bank_operations: FinanceWorkspaceOperationRow[];
  financial_operations: FinanceWorkspaceOperationRow[];
  returns: FinanceWorkspaceReturnRow[];
  accounts: FinanceWorkspaceAccountRow[];
};

export type FinanceWorkspaceResponse = {
  period: AnalyticsPeriodWindow;
  active_view: FinanceWorkspaceView;
  summary: FinanceWorkspaceSummary;
  coverage: FinanceWorkspaceCoverageItem[];
  tabs: FinanceWorkspaceTabStatus[];
  filters: FinanceWorkspaceFiltersMetadata;
  data_quality: AnalyticsDataQualityReport;
  rows: FinanceWorkspaceRows;
  pagination: FinanceWorkspacePagination;
};

export type FinanceWorkspaceFilters = {
  organizationId?: string | null;
  organizationIds?: string[];
  dateFrom?: string | null;
  dateTo?: string | null;
  period?: AnalyticsPeriodPreset;
  comparisonMode?: AnalyticsComparisonMode;
  view?: FinanceWorkspaceView;
  search?: string | null;
  direction?: FinanceWorkspaceDirection[];
  operationType?: string[];
  paymentType?: string[];
  counterparty?: string[];
  account?: string[];
  currency?: string[];
  dataQuality?: Array<"verified" | "partial" | "unresolved" | "unsafe">;
  amountMin?: string | number | null;
  amountMax?: string | number | null;
  sortBy?: FinanceWorkspaceSortBy;
  sortOrder?: FinanceWorkspaceSortOrder;
  page?: number;
  pageSize?: number;
};

// Browser requests stay same-origin so remote users never resolve localhost
// against their own machine. Server-side callers may still use the local API.
const coreApiBaseUrl = typeof window === "undefined"
  ? (process.env.CORE_API_URL ?? "http://127.0.0.1:8000")
  : "";
// Ordinary API reads must tolerate local load and the domain proxy hop.
// AI Chat streaming has a separate lifecycle and never uses this timeout.
const fastReadTimeoutMs = 12_000;
const requestTimeoutMs = 20_000;

export type CoreApiRequestErrorKind = "timeout" | "http" | "network" | "aborted";

export class CoreApiRequestError extends Error {
  readonly kind: CoreApiRequestErrorKind;
  readonly status?: number;

  constructor(message: string, kind: CoreApiRequestErrorKind, status?: number) {
    super(message);
    this.name = "CoreApiRequestError";
    this.kind = kind;
    this.status = status;
  }
}

function ownerSessionToken() {
  if (typeof document === "undefined") return null;
  return document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=") ?? null;
}

function authenticatedHeaders(headers?: HeadersInit) {
  const token = ownerSessionToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${decodeURIComponent(token)}` } : {}),
    ...(headers ?? {}),
  };
}

export type AiChatMessage = {
  role: "system" | "user" | "assistant";
  content: string | Array<
    | { type: "text"; text: string }
    | { type: "image_url"; image_url: { url: string } }
  >;
};

export type AiProviderModel = {
  id: string;
  name: string;
  available?: boolean;
};

export type AiProvider = {
  id: string;
  provider: string;
  model: string;
  name: string;
  status: "available" | "unavailable" | "not_configured";
  available: boolean;
  capabilities?: string[];
};

export async function getAiProviders(): Promise<AiProvider[]> {
  return requestJson<AiProvider[]>("/api/v1/ai/providers", {}, 10_000);
}

export type AiRoutingAssignment = {
  primary_provider_id: string | null;
  primary_model_id: string | null;
  fallback_provider_id: string | null;
  fallback_model_id: string | null;
};

export type AiRoutingConfig = {
  roles: Record<string, AiRoutingAssignment>;
  business_analytics_auto_enabled?: boolean;
  business_analytics_triggers?: string[];
};

export type AiRoutingResponse = {
  providers: Array<{
    id: string;
    provider: string;
    model: string;
    name: string;
    status: "available" | "unavailable" | "not_configured";
    available: boolean;
  }>;
  config: AiRoutingConfig;
  malformed?: boolean;
};

const emptyAiRoutingAssignment = (): AiRoutingAssignment => ({
  primary_provider_id: null,
  primary_model_id: null,
  fallback_provider_id: null,
  fallback_model_id: null,
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeAiRoutingProvider(value: unknown): AiRoutingResponse["providers"][number] | null {
  if (!isRecord(value)) return null;
  const id = typeof value.id === "string" ? value.id : "";
  const provider = typeof value.provider === "string" ? value.provider : "";
  const model = typeof value.model === "string" ? value.model : "";
  if (!id || !provider || !model) return null;
  const status = value.status === "available" || value.status === "unavailable" || value.status === "not_configured"
    ? value.status
    : value.available === true ? "available" : "unavailable";
  return {
    id,
    provider,
    model,
    name: typeof value.name === "string" && value.name ? value.name : model,
    status,
    available: value.available === true && status === "available",
  };
}

function normalizeAiRoutingAssignment(value: unknown): AiRoutingAssignment {
  if (!isRecord(value)) return emptyAiRoutingAssignment();
  const stringOrNull = (candidate: unknown) => typeof candidate === "string" && candidate ? candidate : null;
  return {
    primary_provider_id: stringOrNull(value.primary_provider_id),
    primary_model_id: stringOrNull(value.primary_model_id),
    fallback_provider_id: stringOrNull(value.fallback_provider_id),
    fallback_model_id: stringOrNull(value.fallback_model_id),
  };
}

function normalizeAiRoutingResponse(value: unknown): AiRoutingResponse {
  const payload = isRecord(value) ? value : {};
  const rawProviders = Array.isArray(payload.providers) ? payload.providers : [];
  const providers = rawProviders.map(normalizeAiRoutingProvider).filter((provider): provider is NonNullable<typeof provider> => provider !== null);
  const rawConfig = isRecord(payload.config) ? payload.config : {};
  const rawRoles = isRecord(rawConfig.roles) ? rawConfig.roles : {};
  const roles = Object.fromEntries(Object.entries(rawRoles).map(([role, assignment]) => [role, normalizeAiRoutingAssignment(assignment)]));
  const triggers = Array.isArray(rawConfig.business_analytics_triggers)
    ? rawConfig.business_analytics_triggers.filter((trigger): trigger is string => typeof trigger === "string")
    : [];
  return {
    providers,
    config: {
      roles,
      business_analytics_auto_enabled: rawConfig.business_analytics_auto_enabled === true,
      business_analytics_triggers: triggers,
    },
    malformed: !isRecord(value) || !Array.isArray(payload.providers) || !isRecord(payload.config) || !isRecord(rawConfig.roles),
  };
}

export async function getAiRouting(): Promise<AiRoutingResponse> {
  const payload = await requestJson<unknown>("/api/v1/ai/routing", {}, 10_000);
  return normalizeAiRoutingResponse(payload);
}

export type SessionLockSettings = {
  timeout_minutes: number;
};

export function getSessionLockSettings(): Promise<SessionLockSettings> {
  return requestJson<SessionLockSettings>("/api/v1/auth/lock-settings");
}

export function saveSessionLockSettings(timeoutMinutes: number): Promise<SessionLockSettings> {
  return requestJson<SessionLockSettings>("/api/v1/auth/lock-settings", {
    method: "PUT",
    body: JSON.stringify({ timeout_minutes: timeoutMinutes }),
  });
}

export function lockSystem(): Promise<{ locked: boolean }> {
  return requestJson<{ locked: boolean }>("/api/v1/system/lock", { method: "POST" });
}

export function restartSystem(pin: string): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/api/v1/system/restart", {
    method: "POST",
    body: JSON.stringify({ pin }),
  });
}

export function shutdownSystem(pin: string): Promise<{ status: string }> {
  return requestJson<{ status: string }>("/api/v1/system/shutdown", {
    method: "POST",
    body: JSON.stringify({ pin }),
  });
}

export async function saveAiRouting(config: AiRoutingConfig): Promise<AiRoutingResponse> {
  const payload = await requestJson<unknown>("/api/v1/ai/routing", {
    method: "PUT",
    body: JSON.stringify(config),
  }, 10_000);
  return normalizeAiRoutingResponse(payload);
}

export type DashboardAIInsight = {
  type: string;
  title: string;
  description: string;
  priority: "low" | "medium" | "high" | "critical";
  reason?: string;
  affected_entity?: string | null;
  affected_metric?: string | null;
  evidence?: Array<Record<string, unknown>>;
};

export type DashboardAIInsightsResponse = {
  analysis_id: string | null;
  generated_at: string | null;
  summary: string | null;
  status?: string;
  message?: string;
  findings: Array<Record<string, unknown>>;
  opportunities: Array<Record<string, unknown>>;
  recommendations: Array<Record<string, unknown>>;
  provider_id?: string | null;
  model_id?: string | null;
  organization_ids?: string[];
  period?: Record<string, unknown>;
  items: DashboardAIInsight[];
};

export type DashboardAIAnalysisStatus = {
  status: "idle" | "analyzing" | "completed" | "retry_wait" | "error" | "disabled" | string;
  last_started_at?: string | null;
  last_completed_at?: string | null;
  last_error?: string | null;
  provider_id?: string | null;
  model_id?: string | null;
};

export async function getDashboardAIAnalysisStatus(): Promise<DashboardAIAnalysisStatus> {
  const payload = await requestJson<unknown>("/api/v1/ai/insights/status", {}, 10_000);
  const response = isRecord(payload) ? payload : {};
  return {
    status: typeof response.status === "string" ? response.status : "idle",
    last_started_at: typeof response.last_started_at === "string" ? response.last_started_at : null,
    last_completed_at: typeof response.last_completed_at === "string" ? response.last_completed_at : null,
    last_error: typeof response.last_error === "string" ? response.last_error : null,
    provider_id: typeof response.provider_id === "string" ? response.provider_id : null,
    model_id: typeof response.model_id === "string" ? response.model_id : null,
  };
}

function normalizeDashboardAIInsight(value: unknown): DashboardAIInsight | null {
  if (!isRecord(value)) return null;
  const priority = value.priority === "low" || value.priority === "medium" || value.priority === "high" || value.priority === "critical"
    ? value.priority
    : "medium";
  const stringOrEmpty = (candidate: unknown) => typeof candidate === "string" ? candidate : "";
  return {
    type: stringOrEmpty(value.type) || "finding",
    title: stringOrEmpty(value.title) || "AI insight",
    description: stringOrEmpty(value.description),
    priority,
    reason: typeof value.reason === "string" ? value.reason : undefined,
    affected_entity: typeof value.affected_entity === "string" ? value.affected_entity : null,
    affected_metric: typeof value.affected_metric === "string" ? value.affected_metric : null,
    evidence: Array.isArray(value.evidence) ? value.evidence.filter(isRecord) : [],
  };
}

export async function getDashboardAIInsights(): Promise<DashboardAIInsightsResponse> {
  const payload = await requestJson<unknown>("/api/v1/ai/insights/dashboard", {}, 10_000);
  const response = isRecord(payload) ? payload : {};
  const rawItems = Array.isArray(response.items) ? response.items : [];
  const items = rawItems
    .map(normalizeDashboardAIInsight)
    .filter((item): item is DashboardAIInsight => item !== null);
  return {
    analysis_id: typeof response.analysis_id === "string" ? response.analysis_id : null,
    generated_at: typeof response.generated_at === "string" ? response.generated_at : null,
    summary: typeof response.summary === "string" ? response.summary : null,
    status: typeof response.status === "string" ? response.status : "empty",
    message: typeof response.message === "string" ? response.message : undefined,
    findings: Array.isArray(response.findings) ? response.findings.filter(isRecord) : [],
    opportunities: Array.isArray(response.opportunities) ? response.opportunities.filter(isRecord) : [],
    recommendations: Array.isArray(response.recommendations) ? response.recommendations.filter(isRecord) : [],
    provider_id: typeof response.provider_id === "string" ? response.provider_id : null,
    model_id: typeof response.model_id === "string" ? response.model_id : null,
    organization_ids: Array.isArray(response.organization_ids) ? response.organization_ids.filter((item): item is string => typeof item === "string") : [],
    period: isRecord(response.period) ? response.period : {},
    items,
  };
}

export async function runDashboardAIAnalysis(): Promise<unknown> {
  return requestJson<unknown>("/api/v1/ai/insights/analyze", { method: "POST" }, 15_000);
}

export type WidgetBuilderChatResponse = {
  conversation_id: string;
  assistant_message: string;
  widget_draft: Record<string, unknown> | null;
  clarification_required: boolean;
  clarification_options: string[];
  preview?: Record<string, unknown> | null;
};

export type WidgetBuilderContextResponse = {
  current_context: Record<string, unknown>;
  organizations: Array<Record<string, unknown>>;
  widget_specs: Array<Record<string, unknown>>;
  saved_configs: Array<Record<string, unknown>>;
};

export async function getWidgetBuilderContext(payload: {
  organizationId?: string | null;
  period?: string | null;
} = {}): Promise<WidgetBuilderContextResponse> {
  const params = new URLSearchParams();
  if (payload.organizationId) params.set("organization_id", payload.organizationId);
  if (payload.period) params.set("period", payload.period);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<WidgetBuilderContextResponse>(`/api/v1/dashboard/widget-builder/context${suffix}`);
}

export async function runWidgetBuilderChat(payload: {
  conversationId?: string;
  message: string;
  draft?: Record<string, unknown> | null;
  organizationId?: string | null;
  period?: string | null;
}): Promise<WidgetBuilderChatResponse> {
  return requestJson<WidgetBuilderChatResponse>("/api/v1/dashboard/widget-builder/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: payload.conversationId,
      message: payload.message,
      draft: payload.draft ?? null,
      organization_id: payload.organizationId ?? null,
      period: payload.period ?? null,
    }),
  }, 60_000);
}

export type WidgetBuilderConfirmResponse = {
  config: Record<string, unknown>;
  preview?: Record<string, unknown> | null;
  dashboard_widget?: Record<string, unknown> | null;
};

export async function confirmWidgetBuilder(payload: {
  draft: Record<string, unknown>;
  conversationId?: string;
}): Promise<WidgetBuilderConfirmResponse> {
  return requestJson<WidgetBuilderConfirmResponse>("/api/v1/dashboard/widget-builder/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      draft: payload.draft,
      conversation_id: payload.conversationId,
      source_channel: "web",
    }),
  }, 30_000);
}

export async function deleteWidgetBuilderWidget(widgetId: string): Promise<void> {
  await requestJson("/api/v1/dashboard/widget-builder/delete", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId }),
  }, 15_000);
}

export async function streamAiChat(
  messages: AiChatMessage[],
  onChunk: (content: string) => void,
  signal?: AbortSignal,
  taskType: "business_analytics" | "system_action" | "communications" | "ai_chat" = "ai_chat",
  providerId?: string,
  modelId?: string,
  onMeta?: (meta: { provider_id?: string; provider_name?: string; model_id?: string }) => void,
  conversationId?: string,
  organizationId?: string | null,
  period?: string | null,
  // Progress hook: "thinking" | "researching" | "writing" — purely cosmetic,
  // lets the UI show something more useful than a static "AI is thinking".
  onStage?: (stage: string) => void,
): Promise<void> {
  const response = await fetch(`${coreApiBaseUrl}/api/v1/ai/chat`, {
    method: "POST",
    headers: authenticatedHeaders(),
    body: JSON.stringify({
      messages,
      conversation_id: conversationId,
      task_type: taskType,
      provider: providerId,
      model: modelId,
      organization_id: organizationId,
      period,
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`AI Chat responded with ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let receivedDone = false;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const eventName = event.match(/^event: (.+)$/m)?.[1];
      const data = event.match(/^data: (.+)$/m)?.[1];
      if (!data) continue;
      const payload = JSON.parse(data) as {
        content?: string;
        message?: string;
        provider_id?: string;
        provider_name?: string;
        model_id?: string;
        stage?: string;
      };
      if (eventName === "error") throw new Error(payload.message || "Не удалось получить ответ AI.");
      if (eventName === "meta") onMeta?.(payload);
      if (eventName === "done") receivedDone = true;
      if ((eventName === "stage" || eventName === "heartbeat") && payload.stage) onStage?.(payload.stage);
      if (payload.content) onChunk(payload.content);
    }
    if (done) break;
  }
  if (!receivedDone) {
    throw new Error("AI Chat завершил соединение без готового ответа.");
  }
}

export async function getDashboardOverview(
  filters: DashboardOverviewFilters = {},
): Promise<DashboardOverviewResponse> {
  const params = new URLSearchParams();
  if (filters.businessId) params.set("business_id", filters.businessId);
  if (filters.period) params.set("period", filters.period);
  if (filters.channel) params.set("channel", filters.channel);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<DashboardOverviewResponse>(`/api/v1/dashboard/overview${suffix}`);
}

export async function getDashboardManifest(
  filters: DashboardManifestFilters = {},
): Promise<DashboardManifest> {
  const params = new URLSearchParams();

  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.language) params.set("language", filters.language);
  if (filters.forceRefresh) params.set("force_refresh", "true");
  for (const widgetId of filters.pinnedWidgetIds ?? []) {
    params.append("pinned_widget_ids", widgetId);
  }
  for (const widgetId of filters.hiddenWidgetIds ?? []) {
    params.append("hidden_widget_ids", widgetId);
  }
  for (const widgetId of filters.lockedPositionWidgetIds ?? []) {
    params.append("locked_position_widget_ids", widgetId);
  }
  for (const widgetId of filters.lockedSizeWidgetIds ?? []) {
    params.append("locked_size_widget_ids", widgetId);
  }
  for (const widgetId of filters.customWidgetIds ?? []) {
    params.append("custom_widget_ids", widgetId);
  }

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<DashboardManifest>(`/api/v1/dashboard/manifest${suffix}`, {}, 15_000);
}

export async function getDashboardLauncherState(): Promise<DashboardLauncherState> {
  // Launcher persistence can briefly contend with backend startup/sync. It is
  // auxiliary state and should not use the short default data-request timeout.
  return requestJson<DashboardLauncherState>("/api/v1/dashboard/launcher-state", {}, 10_000);
}

export async function saveDashboardLauncherState(payload: DashboardLauncherState): Promise<DashboardLauncherState> {
  return requestJson<DashboardLauncherState>("/api/v1/dashboard/launcher-state", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getOrganizationContext(): Promise<AnalyticsContextState> {
  return requestJson<AnalyticsContextState>("/api/v1/organization-context");
}

export async function updateOrganizationContext(
  payload: AnalyticsContextUpdate,
): Promise<AnalyticsContextState> {
  return requestJson<AnalyticsContextState>("/api/v1/organization-context", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function resetOrganizationContext(): Promise<AnalyticsContextState> {
  return requestJson<AnalyticsContextState>("/api/v1/organization-context", {
    method: "DELETE",
  });
}

export async function getAnalyticsOrganizations(
  filters: {
    organizationId?: string | null;
    organizationIds?: string[];
    dateFrom?: string | null;
    dateTo?: string | null;
    period?: AnalyticsPeriodPreset;
    comparisonMode?: AnalyticsComparisonMode;
  } = {},
): Promise<AnalyticsOrganizationReport> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<AnalyticsOrganizationReport>(`/api/v1/analytics/organizations${suffix}`, {}, 15_000);
}

export async function getSalesWorkspace(
  filters: SalesWorkspaceFilters = {},
): Promise<SalesWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.search) params.set("search", filters.search);
  for (const value of filters.status ?? []) {
    params.append("status", value);
  }
  for (const value of filters.customer ?? []) {
    params.append("customer", value);
  }
  if (filters.product) params.set("product", filters.product);
  for (const value of filters.salesRep ?? []) {
    params.append("sales_rep", value);
  }
  for (const value of filters.workingZone ?? []) {
    params.append("working_zone", value);
  }
  if (typeof filters.realised === "boolean") params.set("realised", String(filters.realised));
  if (typeof filters.hasReturns === "boolean") params.set("has_returns", String(filters.hasReturns));
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.amountMin !== undefined && filters.amountMin !== null) {
    params.set("amount_min", String(filters.amountMin));
  }
  if (filters.amountMax !== undefined && filters.amountMax !== null) {
    params.set("amount_max", String(filters.amountMax));
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<SalesWorkspaceResponse>(`/api/v1/sales${suffix}`, {}, 15_000);
}

export async function getSalesWorkspaceDetail(
  recordId: string,
  filters: Omit<
    SalesWorkspaceFilters,
    | "search"
    | "status"
    | "customer"
    | "product"
    | "salesRep"
    | "workingZone"
    | "realised"
    | "hasReturns"
    | "dataQuality"
    | "amountMin"
    | "amountMax"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<SalesWorkspaceDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<SalesWorkspaceDetail>(`/api/v1/sales/${recordId}${suffix}`, {}, 15_000);
}

export async function getCustomerWorkspace(
  filters: CustomerWorkspaceFilters = {},
): Promise<CustomerWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.search) params.set("search", filters.search);
  if (typeof filters.hasSales === "boolean") params.set("has_sales", String(filters.hasSales));
  if (typeof filters.hasPayments === "boolean") {
    params.set("has_payments", String(filters.hasPayments));
  }
  if (typeof filters.hasReturns === "boolean") {
    params.set("has_returns", String(filters.hasReturns));
  }
  if (typeof filters.hasVisits === "boolean") params.set("has_visits", String(filters.hasVisits));
  for (const value of filters.customerType ?? []) {
    params.append("customer_type", value);
  }
  for (const value of filters.salesRep ?? []) {
    params.append("sales_rep", value);
  }
  for (const value of filters.workingZone ?? []) {
    params.append("working_zone", value);
  }
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.revenueMin !== undefined && filters.revenueMin !== null) {
    params.set("revenue_min", String(filters.revenueMin));
  }
  if (filters.revenueMax !== undefined && filters.revenueMax !== null) {
    params.set("revenue_max", String(filters.revenueMax));
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<CustomerWorkspaceResponse>(`/api/v1/customers${suffix}`, {}, 15_000);
}

export async function getCustomerWorkspaceDetail(
  customerId: string,
  filters: Omit<
    CustomerWorkspaceFilters,
    | "search"
    | "hasSales"
    | "hasPayments"
    | "hasReturns"
    | "hasVisits"
    | "customerType"
    | "salesRep"
    | "workingZone"
    | "dataQuality"
    | "revenueMin"
    | "revenueMax"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<CustomerWorkspaceDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<CustomerWorkspaceDetail>(
    `/api/v1/customers/${customerId}${suffix}`,
    {},
    15_000,
  );
}

export async function getVisitsWorkspace(
  filters: VisitsWorkspaceFilters = {},
): Promise<VisitsWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.tab) params.set("tab", filters.tab);
  if (filters.search) params.set("search", filters.search);
  for (const value of filters.customer ?? []) {
    params.append("customer", value);
  }
  for (const value of filters.salesRep ?? []) {
    params.append("sales_rep", value);
  }
  for (const value of filters.workingZone ?? []) {
    params.append("working_zone", value);
  }
  for (const value of filters.status ?? []) {
    params.append("status", value);
  }
  for (const value of filters.planned ?? []) {
    params.append("planned", value);
  }
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<VisitsWorkspaceResponse>(`/api/v1/visits${suffix}`, {}, 15_000);
}

export async function getVisitsWorkspaceDetail(
  visitId: string,
  filters: Omit<
    VisitsWorkspaceFilters,
    | "tab"
    | "search"
    | "customer"
    | "salesRep"
    | "workingZone"
    | "status"
    | "planned"
    | "dataQuality"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<VisitsWorkspaceDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<VisitsWorkspaceDetail>(`/api/v1/visits/${visitId}${suffix}`, {}, 15_000);
}

export async function getProductWorkspace(
  filters: ProductWorkspaceFilters = {},
): Promise<ProductWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.search) params.set("search", filters.search);
  for (const value of filters.categoryIds ?? []) {
    params.append("category_id", value);
  }
  for (const value of filters.stockStatus ?? []) {
    params.append("stock_status", value);
  }
  if (typeof filters.hasSales === "boolean") params.set("has_sales", String(filters.hasSales));
  if (typeof filters.hasReturns === "boolean") {
    params.set("has_returns", String(filters.hasReturns));
  }
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.revenueMin !== undefined && filters.revenueMin !== null) {
    params.set("revenue_min", String(filters.revenueMin));
  }
  if (filters.revenueMax !== undefined && filters.revenueMax !== null) {
    params.set("revenue_max", String(filters.revenueMax));
  }
  if (filters.soldUnitsMin !== undefined && filters.soldUnitsMin !== null) {
    params.set("sold_units_min", String(filters.soldUnitsMin));
  }
  if (filters.soldUnitsMax !== undefined && filters.soldUnitsMax !== null) {
    params.set("sold_units_max", String(filters.soldUnitsMax));
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ProductWorkspaceResponse>(`/api/v1/products${suffix}`, {}, 15_000);
}

export async function getProductWorkspaceDetail(
  productId: string,
  filters: Omit<
    ProductWorkspaceFilters,
    | "search"
    | "categoryIds"
    | "stockStatus"
    | "hasSales"
    | "hasReturns"
    | "dataQuality"
    | "revenueMin"
    | "revenueMax"
    | "soldUnitsMin"
    | "soldUnitsMax"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<ProductWorkspaceDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ProductWorkspaceDetail>(
    `/api/v1/products/${productId}${suffix}`,
    {},
    15_000,
  );
}

export async function getInventoryWorkspace(
  filters: InventoryWorkspaceFilters = {},
): Promise<InventoryWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.view) params.set("view", filters.view);
  if (filters.search) params.set("search", filters.search);
  for (const value of filters.warehouseId ?? []) {
    params.append("warehouse_id", value);
  }
  for (const value of filters.productId ?? []) {
    params.append("product_id", value);
  }
  for (const value of filters.categoryId ?? []) {
    params.append("category_id", value);
  }
  for (const value of filters.stockStatus ?? []) {
    params.append("stock_status", value);
  }
  if (typeof filters.hasStock === "boolean") params.set("has_stock", String(filters.hasStock));
  if (typeof filters.zeroStock === "boolean") params.set("zero_stock", String(filters.zeroStock));
  if (typeof filters.negativeStock === "boolean") {
    params.set("negative_stock", String(filters.negativeStock));
  }
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<InventoryWorkspaceResponse>(`/api/v1/inventory${suffix}`, {}, 15_000);
}

export async function getFinanceWorkspace(
  filters: FinanceWorkspaceFilters = {},
): Promise<FinanceWorkspaceResponse> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  if (filters.view) params.set("view", filters.view);
  if (filters.search) params.set("search", filters.search);
  for (const value of filters.direction ?? []) {
    params.append("direction", value);
  }
  for (const value of filters.operationType ?? []) {
    params.append("operation_type", value);
  }
  for (const value of filters.paymentType ?? []) {
    params.append("payment_type", value);
  }
  for (const value of filters.counterparty ?? []) {
    params.append("counterparty", value);
  }
  for (const value of filters.account ?? []) {
    params.append("account", value);
  }
  for (const value of filters.currency ?? []) {
    params.append("currency", value);
  }
  for (const value of filters.dataQuality ?? []) {
    params.append("data_quality", value);
  }
  if (filters.amountMin !== undefined && filters.amountMin !== null && filters.amountMin !== "") {
    params.set("amount_min", String(filters.amountMin));
  }
  if (filters.amountMax !== undefined && filters.amountMax !== null && filters.amountMax !== "") {
    params.set("amount_max", String(filters.amountMax));
  }
  if (filters.sortBy) params.set("sort_by", filters.sortBy);
  if (filters.sortOrder) params.set("sort_order", filters.sortOrder);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<FinanceWorkspaceResponse>(`/api/v1/finance${suffix}`, {}, 15_000);
}

export async function getInventoryCurrentStockDetail(
  inventoryBalanceId: string,
  filters: Omit<
    InventoryWorkspaceFilters,
    | "view"
    | "search"
    | "warehouseId"
    | "productId"
    | "categoryId"
    | "stockStatus"
    | "hasStock"
    | "zeroStock"
    | "negativeStock"
    | "dataQuality"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<InventoryWorkspaceCurrentStockDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<InventoryWorkspaceCurrentStockDetail>(
    `/api/v1/inventory/current-stock/${inventoryBalanceId}${suffix}`,
    {},
    15_000,
  );
}

export async function getInventoryWarehouseDetail(
  warehouseKey: string,
  filters: Omit<
    InventoryWorkspaceFilters,
    | "view"
    | "search"
    | "warehouseId"
    | "productId"
    | "categoryId"
    | "stockStatus"
    | "hasStock"
    | "zeroStock"
    | "negativeStock"
    | "dataQuality"
    | "sortBy"
    | "sortOrder"
    | "page"
    | "pageSize"
  > = {},
): Promise<InventoryWorkspaceWarehouseDetail> {
  const params = new URLSearchParams();
  if (filters.organizationId) params.set("organization_id", filters.organizationId);
  for (const organizationId of filters.organizationIds ?? []) {
    params.append("organization_ids", organizationId);
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.period) params.set("period", filters.period);
  if (filters.comparisonMode) params.set("comparison_mode", filters.comparisonMode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<InventoryWorkspaceWarehouseDetail>(
    `/api/v1/inventory/warehouses/${warehouseKey}${suffix}`,
    {},
    15_000,
  );
}

export async function getNotifications(): Promise<NotificationFeedResponse> {
  const response = await requestJson<NotificationFeedResponseApi>("/api/v1/notifications");

  return {
    generated_at: response.generated_at,
    unread_count: response.unread_count,
    total_count: response.total_count,
    items: response.items.map((item) => ({
      id: item.id,
      title: item.title,
      message: item.message,
      time: item.time,
      tag: item.tag,
      tone: item.tone,
      unread: item.unread,
      read: item.read,
      actionLabel: item.action_label,
      detailsHref: item.details_href,
    })),
  };
}

export async function getNotification(notificationId: string): Promise<NotificationItem> {
  const item = await requestJson<NotificationItemApi>(`/api/v1/notifications/${notificationId}`);

  return {
    id: item.id,
    title: item.title,
    message: item.message,
    time: item.time,
    tag: item.tag,
    tone: item.tone,
    unread: item.unread,
    read: item.read,
    actionLabel: item.action_label,
    detailsHref: item.details_href,
  };
}

export async function markNotificationRead(notificationId: string): Promise<NotificationMutationResponse> {
  return requestJson<NotificationMutationResponse>(`/api/v1/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export async function markAllNotificationsRead(): Promise<NotificationMutationResponse> {
  return requestJson<NotificationMutationResponse>("/api/v1/notifications/read-all", {
    method: "POST",
  });
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = requestTimeoutMs,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${coreApiBaseUrl}${path}`, {
      cache: "no-store",
      ...init,
      headers: authenticatedHeaders(init.headers),
      signal: controller.signal,
    });

    if (!response.ok) {
      const message = await response.text();
      throw new CoreApiRequestError(
        `${path} responded with ${response.status}${message ? `: ${message}` : ""}`,
        "http",
        response.status,
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (path === "/api/v1/dashboard/overview") {
      return createFallbackOverview() as T;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new CoreApiRequestError(`Request to ${path} was aborted by timeout`, "timeout");
    }
    if (error instanceof CoreApiRequestError) {
      throw error;
    }
    if (error instanceof TypeError) {
      throw new CoreApiRequestError(`Request to ${path} failed because of a network error`, "network");
    }
    if (error instanceof Error) {
      throw error;
    }
    throw new Error(`Request to ${path} failed`);
  } finally {
    clearTimeout(timeoutId);
  }
}

function createFallbackOverview(): DashboardOverviewResponse {
  return {
    generated_at: new Date().toISOString(),
    analysis_engine: "AI Business Core",
    analysis_note: "Сводка строится по данным бизнеса: продажи, деньги, товары и организации.",
    freshness: "Нет загруженной истории",
    data_summary: [
      { label: "Выручка", value: "0 UZS", note: "по продажам за выбранный период" },
      { label: "Получено денег", value: "0 UZS", note: "по платежам и поступлениям" },
      { label: "Расходы", value: "0 UZS", note: "по финансовым операциям" },
      { label: "Чистый поток", value: "0 UZS", note: "разница поступлений и расходов" },
      { label: "Продано единиц", value: "0", note: "количество товаров в продажах" },
      { label: "Сделок", value: "0", note: "подтвержденные продажи" },
      { label: "Товаров", value: "0", note: "позиции ассортимента" },
      { label: "Организаций", value: "0", note: "подключённые филиалы SmartUp" },
    ],
    executive_summary: [
      {
        label: "Выручка",
        value: "0",
        note: "за выбранный период",
      },
      {
        label: "Сделки",
        value: "0",
        note: "подтверждённые продажи",
      },
      {
        label: "Платежи",
        value: "0",
        note: "поступления из финансов",
      },
      {
        label: "Обновление",
        value: "Нет данных",
        note: "данные ещё не загружены",
      },
    ],
    business_metrics: [
      { label: "Выручка", value: "0 UZS", note: "только подтверждённые продажи" },
      { label: "Получено денег", value: "0 UZS", note: "по платежам и поступлениям" },
      { label: "Расходы", value: "0 UZS", note: "по расходным операциям" },
      { label: "Чистый поток", value: "0 UZS", note: "разница поступлений и расходов" },
      { label: "Продано единиц", value: "0", note: "количество строк SaleItem" },
      { label: "Средний чек", value: "0 UZS", note: "выручка на одну сделку" },
    ],
    trend: {
      title: "Динамика продаж",
      description: "Выручка и поток по продажам за последние 12 месяцев.",
      badge: "Без данных",
      labels: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
      values: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
    signals: [
      {
        title: "История ещё не загружена",
        badge: "Пусто",
        note: "Подключите организацию и загрузите бизнес-историю.",
      },
      {
        title: "Денежный поток не рассчитан",
        badge: "Финансы",
        note: "После загрузки данных здесь появится финансовая сводка.",
      },
      {
        title: "Воронка пока пустая",
        badge: "Продажи",
        note: "Когда появятся сделки, экран покажет активные и закрытые этапы.",
      },
      {
        title: "Маркетинг ещё не заполнен",
        badge: "Рост",
        note: "После загрузки данных появятся каналы, бюджеты и конверсии.",
      },
    ],
    structure: [
      {
        label: "Продажи",
        value: "0%",
        note: "0 записей • 0 закрыто",
        color: "#6d5efc",
      },
      {
        label: "Финансы",
        value: "0%",
        note: "0 записей • 0 доходов",
        color: "#0ea5e9",
      },
      {
        label: "Маркетинг",
        value: "0%",
        note: "0 записей • 0 конверсий",
        color: "#10b981",
      },
      {
        label: "Контакты",
        value: "0%",
        note: "0 записей • связанные CRM-записи",
        color: "#a78bfa",
      },
    ],
    action_center: [],
    organization_performance: [],
    dead_stock: [],
    returns_summary: [],
    cash_flow: [],
    customers_summary: [],
    seller_performance: [],
    recommendations: [],
    availability: [],
    businesses: [],
    recent_sales: [],
    top_products: [],
    inventory: [],
    recent_payments: [],
    ai_insights: [
      "В базе пока нет полной истории.",
      "После загрузки здесь появятся реальные бизнес-метрики.",
      "Сводка строится на продажах, финансах и маркетинге из Core API.",
      "Свежесть ядра: история не загружена.",
    ],
  };
}

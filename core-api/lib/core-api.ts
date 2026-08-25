export type DashboardCard = {
  label: string;
  value: string;
  note: string;
  details_href?: string | null;
  status?: "available" | "partial" | "unavailable" | "syncing" | "error";
  previous_value?: string | null;
  change?: string | null;
};

export type SmartUpLiveSyncGroupStatus = {
  group: string;
  interval_seconds: number;
  overlap_seconds: number;
  mappings: string[];
  due: boolean;
  last_sync_at?: string | null;
  next_sync_at?: string | null;
  last_status: string;
  last_error?: string | null;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  batches: number;
  records: number;
  errors: number;
};

export type SmartUpLiveSyncOrganizationStatus = {
  organization_id: string;
  organization_name: string;
  company_id: string;
  filial_id: string;
  project_code: string;
  last_sync_at?: string | null;
  groups: SmartUpLiveSyncGroupStatus[];
};

export type SmartUpLiveSyncStatusResponse = {
  enabled: boolean;
  running: boolean;
  started_at?: string | null;
  last_tick_at?: string | null;
  poll_interval_seconds: number;
  transaction_interval_seconds: number;
  reference_interval_seconds: number;
  overlap_seconds: number;
  organizations_count: number;
  organizations: SmartUpLiveSyncOrganizationStatus[];
  last_error?: string | null;
};

export type ApiQueryValue = string | number | boolean | null | undefined | Array<string | number | boolean>;
export type ApiQuery = Record<string, ApiQueryValue>;

export type CoreApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
};

export type WorkspaceName =
  | "dashboard"
  | "sales"
  | "customers"
  | "products"
  | "inventory"
  | "finance"
  | "visits"
  | "smartup";

export type BusinessContextState = {
  organization_context: {
    mode: "all" | "single" | "multiple";
    organization_ids: string[];
  };
  period_context: {
    preset: string;
    date_from?: string | null;
    date_to?: string | null;
  };
  saved_at: string;
};

export function resolveCoreApiBaseUrl(baseUrl?: string): string {
  const runtimeEnv = globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
    __CORE_API_BASE_URL__?: string;
  };
  const resolved = (
    baseUrl ??
    runtimeEnv.process?.env?.NEXT_PUBLIC_CORE_API_BASE_URL ??
    runtimeEnv.process?.env?.CORE_API_BASE_URL ??
    runtimeEnv.__CORE_API_BASE_URL__ ??
    ""
  ).trim();
  return resolved.replace(/\/$/, "");
}

export function buildApiUrl(path: string, query?: ApiQuery, baseUrl?: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const origin =
    resolveCoreApiBaseUrl(baseUrl) ||
    (typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:8000");
  const url = new URL(normalizedPath, origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value == null) {
        continue;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, String(item));
        }
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export function normalizeQuery(query?: ApiQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (!query) {
    return params;
  }
  for (const [key, value] of Object.entries(query)) {
    if (value == null) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, String(item));
      }
      continue;
    }
    params.set(key, String(value));
  }
  return params;
}

export function createCoreApiClient(options: CoreApiClientOptions = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const baseUrl = resolveCoreApiBaseUrl(options.baseUrl);

  async function requestJson<T>(path: string, query?: ApiQuery, init?: RequestInit): Promise<T> {
    const url = buildApiUrl(path, query, baseUrl);
    const response = await fetchImpl(url, {
      cache: "no-store",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Request to ${url} failed with ${response.status}: ${body}`);
    }
    return (await response.json()) as T;
  }

  return {
    baseUrl,
    requestJson,
    getDashboardOverview: (query?: ApiQuery) => requestJson<unknown>("/api/v1/dashboard/overview", query),
    getDashboardExecutiveWorkspace: (query?: ApiQuery) =>
      requestJson<unknown>("/api/v1/dashboard/executive-workspace", query),
    getDashboardManifest: (query?: ApiQuery) => requestJson<unknown>("/api/v1/dashboard/manifest", query),
    getGlobalContext: () => requestJson<BusinessContextState>("/api/v1/organization-context"),
    getLiveSyncStatus: () => requestJson<SmartUpLiveSyncStatusResponse>("/api/v1/smartup/live-sync/status"),
    getSalesWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/sales", query),
    getSalesWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/sales/${recordId}`, query),
    getCustomersWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/customers", query),
    getCustomersWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/customers/${recordId}`, query),
    getProductsWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/products", query),
    getProductsWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/products/${recordId}`, query),
    getInventoryWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/inventory", query),
    getInventoryWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/inventory/${recordId}`, query),
    getFinanceWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/finance", query),
    getFinanceWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/finance/${recordId}`, query),
    getVisitsWorkspace: (query?: ApiQuery) => requestJson<unknown>("/api/v1/visits", query),
    getVisitsWorkspaceDetail: (recordId: string, query?: ApiQuery) =>
      requestJson<unknown>(`/api/v1/visits/${recordId}`, query),
  };
}

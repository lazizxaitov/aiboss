import { createCoreApiClient, type SmartUpLiveSyncStatusResponse } from "@/lib/core-api";

export type BusinessFreshnessState = "live" | "delayed" | "stale" | "error" | "unknown";

export type BusinessFreshnessSnapshot = {
  state: BusinessFreshnessState;
  label: string;
  status: SmartUpLiveSyncStatusResponse | null;
  updatedAt: string | null;
};

export type WorkspaceRefreshHandler = () => void | Promise<void>;

export type BusinessRefreshControllerOptions = {
  refresh: WorkspaceRefreshHandler;
  onStatusChange?: (snapshot: BusinessFreshnessSnapshot) => void;
  baseUrl?: string;
  visibleIntervalMs?: number;
  hiddenIntervalMs?: number;
  staleAfterSeconds?: number;
};

type ListenerEntry = {
  id: symbol;
  refresh: WorkspaceRefreshHandler;
};

type StatusListener = (snapshot: BusinessFreshnessSnapshot) => void;

function isDocumentVisible() {
  return typeof document === "undefined" ? true : document.visibilityState !== "hidden";
}

function relativeLabel(updatedAt: string | null) {
  if (!updatedAt) {
    return "Обновление...";
  }
  const updated = new Date(updatedAt);
  if (Number.isNaN(updated.getTime())) {
    return "Обновлено";
  }
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - updated.getTime()) / 1000));
  if (deltaSeconds < 10) return "Обновлено только что";
  if (deltaSeconds < 60) return `Обновлено ${deltaSeconds} сек назад`;
  const minutes = Math.floor(deltaSeconds / 60);
  if (minutes < 60) return `Обновлено ${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  return `Обновлено ${hours} ч назад`;
}

export function deriveFreshnessSnapshot(
  status: SmartUpLiveSyncStatusResponse | null,
  staleAfterSeconds = 180,
): BusinessFreshnessSnapshot {
  if (!status) {
    return {
      state: "unknown",
      label: "Обновление...",
      status: null,
      updatedAt: null,
    };
  }

  const updatedAt = status.last_tick_at ?? status.started_at ?? null;
  if (status.last_error) {
    return {
      state: "error",
      label: "Есть задержка синхронизации",
      status,
      updatedAt,
    };
  }

  if (!updatedAt) {
    return {
      state: status.running ? "delayed" : "unknown",
      label: status.running ? "Обновление..." : "Обновлено",
      status,
      updatedAt,
    };
  }

  const updated = new Date(updatedAt);
  const ageSeconds = Math.max(0, Math.floor((Date.now() - updated.getTime()) / 1000));
  if (status.running || ageSeconds <= 60) {
    return {
      state: "live",
      label: relativeLabel(updatedAt),
      status,
      updatedAt,
    };
  }
  if (ageSeconds <= staleAfterSeconds) {
    return {
      state: "delayed",
      label: relativeLabel(updatedAt),
      status,
      updatedAt,
    };
  }
  return {
    state: "stale",
    label: "Есть задержка синхронизации",
    status,
    updatedAt,
  };
}

export class BusinessRefreshController {
  private readonly client = createCoreApiClient({ baseUrl: this.options.baseUrl });
  private readonly listeners = new Map<symbol, ListenerEntry>();
  private readonly statusListeners = new Set<StatusListener>();
  private timer: number | null = null;
  private running = false;
  private visible = isDocumentVisible();
  private lastSnapshot: BusinessFreshnessSnapshot | null = null;

  constructor(private readonly options: BusinessRefreshControllerOptions) {}

  start() {
    if (this.running) return;
    if (typeof window === "undefined") return;
    this.running = true;
    this.bindVisibilityListeners();
    void this.tick();
  }

  stop() {
    this.running = false;
    if (this.timer !== null) {
      if (typeof window !== "undefined") {
        window.clearTimeout(this.timer);
      }
      this.timer = null;
    }
    if (typeof window !== "undefined") {
      window.removeEventListener("focus", this.handleFocus);
      window.removeEventListener("online", this.handleFocus);
      document.removeEventListener("visibilitychange", this.handleVisibilityChange);
    }
  }

  subscribe(refresh: WorkspaceRefreshHandler) {
    const id = Symbol("business-refresh-listener");
    this.listeners.set(id, { id, refresh });
    return () => {
      this.listeners.delete(id);
    };
  }

  subscribeStatus(listener: StatusListener) {
    this.statusListeners.add(listener);
    if (this.lastSnapshot) {
      listener(this.lastSnapshot);
    }
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  async refreshNow() {
    await this.runRefreshCycle(true);
  }

  getSnapshot() {
    return this.lastSnapshot;
  }

  private bindVisibilityListeners() {
    if (typeof window === "undefined") return;
    window.addEventListener("focus", this.handleFocus);
    window.addEventListener("online", this.handleFocus);
    document.addEventListener("visibilitychange", this.handleVisibilityChange);
  }

  private handleFocus = () => {
    this.visible = true;
    void this.runRefreshCycle(true);
  };

  private handleVisibilityChange = () => {
    this.visible = isDocumentVisible();
    if (this.visible) {
      void this.runRefreshCycle(true);
    }
  };

  private async tick() {
    if (!this.running || typeof window === "undefined") return;
    await this.runRefreshCycle(false);
    const delay = this.visible ? this.options.visibleIntervalMs ?? 60000 : this.options.hiddenIntervalMs ?? 180000;
    this.timer = window.setTimeout(() => {
      void this.tick();
    }, delay);
  }

  private async runRefreshCycle(immediate: boolean) {
    try {
      const status = await this.client.getLiveSyncStatus();
      const snapshot = deriveFreshnessSnapshot(status, this.options.staleAfterSeconds ?? 180);
      this.lastSnapshot = snapshot;
      this.options.onStatusChange?.(snapshot);
      for (const listener of this.statusListeners) {
        listener(snapshot);
      }
      if (immediate || snapshot.state === "live" || snapshot.state === "delayed") {
        await Promise.allSettled([...this.listeners.values()].map((entry) => entry.refresh()));
      }
    } catch {
      this.lastSnapshot = {
        state: "error",
        label: "Есть задержка синхронизации",
        status: null,
        updatedAt: null,
      };
      this.options.onStatusChange?.(this.lastSnapshot);
      for (const listener of this.statusListeners) {
        listener(this.lastSnapshot);
      }
    }
  }
}

let sharedController: BusinessRefreshController | null = null;

export function getBusinessRefreshController(options: BusinessRefreshControllerOptions) {
  if (sharedController === null) {
    sharedController = new BusinessRefreshController(options);
    sharedController.start();
  }
  return sharedController;
}

export function resetBusinessRefreshController() {
  sharedController?.stop();
  sharedController = null;
}

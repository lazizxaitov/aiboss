export type BusinessFreshnessState = "live" | "delayed" | "stale" | "error" | "unknown";

export type BusinessFreshnessSnapshot = {
  state: BusinessFreshnessState;
  label: string;
  updatedAt: string | null;
};

export type WorkspaceRefreshHandler = () => void | Promise<void>;

export type BusinessRefreshControllerOptions = {
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

export function deriveFreshnessSnapshot(): BusinessFreshnessSnapshot {
  return {
    state: "unknown",
    label: "Обновлено",
    updatedAt: null,
  };
}

export class BusinessRefreshController {
  private readonly listeners = new Map<symbol, ListenerEntry>();
  private readonly statusListeners = new Set<StatusListener>();
  private timer: number | null = null;
  private running = false;
  private visible = isDocumentVisible();
  private lastSnapshot: BusinessFreshnessSnapshot | null = null;

  constructor(private readonly options: BusinessRefreshControllerOptions = {}) {}

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
    const snapshot: BusinessFreshnessSnapshot = {
      state: "unknown",
      label: "Обновлено",
      updatedAt: null,
    };
    this.lastSnapshot = snapshot;
    for (const listener of this.statusListeners) {
      listener(snapshot);
    }
    if (immediate || snapshot.state === "live" || snapshot.state === "delayed") {
      await Promise.allSettled([...this.listeners.values()].map((entry) => entry.refresh()));
    }
  }
}

let sharedController: BusinessRefreshController | null = null;

export function getBusinessRefreshController(options: BusinessRefreshControllerOptions = {}) {
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

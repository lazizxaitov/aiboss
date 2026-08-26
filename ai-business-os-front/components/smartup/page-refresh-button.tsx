"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { getSmartUpMigrationJob, startSmartUpPageSync, type SmartUpPage } from "@/lib/core-api";

export function SmartUpPageRefreshButton({
  page,
  onCompleted,
}: {
  page: SmartUpPage;
  onCompleted: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = async () => {
    if (running) return;
    setRunning(true);
    setMessage(null);
    try {
      let job = await startSmartUpPageSync(page);
      while (job.status === "pending" || job.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        job = await getSmartUpMigrationJob(job.job_id);
      }
      if (job.status === "failed") throw new Error(job.error ?? "Не удалось обновить данные.");
      setMessage(job.result?.status === "completed_with_errors" ? "Обновлено с предупреждениями" : "Обновлено");
      onCompleted();
    } catch (error) {
      setMessage(error instanceof Error && error.message.includes("SYNC_ALREADY_RUNNING") ? "Синхронизация уже выполняется" : "Не удалось обновить");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" size="md" onClick={() => void refresh()} disabled={running}>
        {running ? "Обновление..." : "Обновить"}
      </Button>
      {message ? <span className="text-xs text-slate-400">{message}</span> : null}
    </div>
  );
}

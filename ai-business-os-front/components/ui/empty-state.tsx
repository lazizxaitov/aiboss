import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
};

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-[24px] border border-dashed border-[#3a3d43] bg-[#2E3137] px-6 py-10 text-center">
      <p className="text-base font-semibold tracking-[-0.03em] text-[#f4f7fb]">{title}</p>
      {description ? <p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

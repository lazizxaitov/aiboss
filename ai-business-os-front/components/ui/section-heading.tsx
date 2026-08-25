import type { ReactNode } from "react";

type SectionHeadingProps = {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function SectionHeading({
  eyebrow,
  title,
  description,
  actions,
}: SectionHeadingProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="max-w-4xl">
        <p className="text-[11px] uppercase tracking-[0.32em] text-slate-400">
          {eyebrow}
        </p>
        <h2 className="mt-2 text-[32px] font-semibold tracking-[-0.06em] text-[#f4f7fb] sm:text-[36px]">
          {title}
        </h2>
        {description ? (
          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300 sm:text-[15px]">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

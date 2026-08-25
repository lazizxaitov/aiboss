type LoadingStateProps = {
  title?: string;
  description?: string;
};

export function LoadingState({
  title = "Загрузка...",
  description = "Подтягиваем данные и строим рабочий экран.",
}: LoadingStateProps) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-[24px] border border-[#3a3d43] bg-[#2E3137] px-6 py-10">
      <div className="text-center">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-[#3a3d43] border-t-[#f4f7fb]" />
        <p className="mt-4 text-base font-semibold tracking-[-0.03em] text-[#f4f7fb]">{title}</p>
        <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
      </div>
    </div>
  );
}

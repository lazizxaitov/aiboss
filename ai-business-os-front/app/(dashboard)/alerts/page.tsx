import { NotificationsCenter } from "@/modules/alerts/notifications-center";

type AlertsPageProps = {
  searchParams?: Promise<{
    item?: string | string[];
  }>;
};

export default async function Page({ searchParams }: AlertsPageProps) {
  const resolvedSearchParams = await searchParams;
  const selectedId = Array.isArray(resolvedSearchParams?.item)
    ? resolvedSearchParams.item[0]
    : resolvedSearchParams?.item;

  return <NotificationsCenter selectedId={selectedId} />;
}

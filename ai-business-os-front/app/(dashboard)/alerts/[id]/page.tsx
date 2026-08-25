import { NotificationDetails } from "@/modules/alerts/notification-details";

type NotificationDetailsPageProps = {
  params: {
    id: string;
  };
};

export default function Page({ params }: NotificationDetailsPageProps) {
  return <NotificationDetails notificationId={params.id} />;
}

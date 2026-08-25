import { telegramModule } from "@/modules/telegram/config";
import { ModuleScreen } from "@/modules/shared/module-screen";

export default function Page() {
  return <ModuleScreen module={telegramModule} />;
}

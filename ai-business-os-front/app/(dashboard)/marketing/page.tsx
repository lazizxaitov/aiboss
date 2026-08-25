import { marketingModule } from "@/modules/marketing/config";
import { ModuleScreen } from "@/modules/shared/module-screen";

export default function Page() {
  return <ModuleScreen module={marketingModule} />;
}

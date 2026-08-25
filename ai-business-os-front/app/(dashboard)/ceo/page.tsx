import { ceoModule } from "@/modules/ceo/config";
import { ModuleScreen } from "@/modules/shared/module-screen";

export default function Page() {
  return <ModuleScreen module={ceoModule} />;
}

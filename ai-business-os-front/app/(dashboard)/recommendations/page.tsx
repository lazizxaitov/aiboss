import { recommendationsModule } from "@/modules/recommendations/config";
import { ModuleScreen } from "@/modules/shared/module-screen";

export default function Page() {
  return <ModuleScreen module={recommendationsModule} />;
}

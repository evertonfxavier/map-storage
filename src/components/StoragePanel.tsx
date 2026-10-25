import { useMapStorage } from "../hooks";
import { AdvancedSection } from "./AdvancedSection";
import { DetailsSection } from "./DetailsSection";
import { DrivesSection } from "./DrivesSection";
import { StatusBanner } from "./StatusBanner";

export function StoragePanel() {
  const model = useMapStorage();
  return (
    <>
      <StatusBanner model={model} />
      <DrivesSection model={model} />
      <AdvancedSection model={model} />
      <DetailsSection model={model} />
    </>
  );
}

import { useMapStorage } from "../hooks";
import { AdvancedSection } from "./AdvancedSection";
import { DetailsSection } from "./DetailsSection";
import { StatusBanner } from "./StatusBanner";
import { StorageSection } from "./StorageSection";

export function StoragePanel() {
  const model = useMapStorage();
  return (
    <>
      <StatusBanner model={model} />
      <StorageSection model={model} />
      <AdvancedSection model={model} />
      <DetailsSection model={model} />
    </>
  );
}

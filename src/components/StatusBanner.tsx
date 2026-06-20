import { PanelSection, PanelSectionRow } from "@decky/ui";
import { StatusCard } from "./StatusCard";
import type { MapStorageModel } from "../hooks";

export function StatusBanner({ model }: { model: MapStorageModel }) {
  const {
    busy,
    isRoot,
    scanError,
    selectedPath,
    isMounted,
    storageName,
    selectedDevice,
    mountTarget,
    serviceActive,
  } = model;

  const sizeSuffix = selectedDevice?.size ? ` · ${selectedDevice.size}` : "";

  const card = (() => {
    if (busy) return <StatusCard tone="info" title="Working…" lines={[]} busy />;

    if (isRoot === false) {
      return (
        <StatusCard
          tone="danger"
          title="No root access"
          lines={[
            "Automount cannot be configured.",
            "Reinstall the plugin (it requests root) and restart Decky.",
          ]}
        />
      );
    }

    if (scanError) {
      return <StatusCard tone="danger" title="Scan failed" lines={[scanError]} />;
    }

    if (!selectedPath) {
      return (
        <StatusCard
          tone="warn"
          title="No storage selected"
          lines={["Tap “Re-scan drives” and choose your library drive."]}
        />
      );
    }

    if (isMounted) {
      return (
        <StatusCard
          tone="ok"
          title="Library ready"
          lines={[
            `${storageName}${sizeSuffix}`,
            `Mounted at ${mountTarget}`,
            serviceActive ? "Automount service active" : "Available in Game Mode",
          ]}
        />
      );
    }

    return (
      <StatusCard
        tone="warn"
        title="Not mounted yet"
        lines={[
          `${storageName}${sizeSuffix}`,
          "Tap “Enable automount” to mount it now and on every boot.",
        ]}
      />
    );
  })();

  return (
    <PanelSection>
      <PanelSectionRow>{card}</PanelSectionRow>
    </PanelSection>
  );
}

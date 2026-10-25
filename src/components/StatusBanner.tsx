import { PanelSection, PanelSectionRow } from "@decky/ui";
import { StatusCard } from "./StatusCard";
import type { MapStorageModel } from "../hooks";

export function StatusBanner({ model }: { model: MapStorageModel }) {
  const { busy, isRoot, scanError, drives, enabledDrives, attentionDrives } = model;

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

    if (!drives.length) {
      return (
        <StatusCard
          tone="warn"
          title="No drives found"
          lines={["Plug in a drive and tap “Re-scan drives”."]}
        />
      );
    }

    if (!enabledDrives.length) {
      return (
        <StatusCard
          tone="info"
          title="No drive enabled"
          lines={["Flip a switch below so Steam can use that drive."]}
        />
      );
    }

    if (attentionDrives.length) {
      return (
        <StatusCard
          tone="warn"
          title="Needs attention"
          lines={attentionDrives.map((d) =>
            d.present
              ? `${d.name}: not mounted — try “Re-apply” in Advanced`
              : `${d.name}: not connected`
          )}
        />
      );
    }

    return (
      <StatusCard
        tone="ok"
        title={enabledDrives.length > 1 ? "Libraries ready" : "Library ready"}
        lines={enabledDrives.map((d) => `${d.name} · ${d.size} · ${d.mountpoint}`)}
      />
    );
  })();

  return (
    <PanelSection>
      <PanelSectionRow>{card}</PanelSectionRow>
    </PanelSection>
  );
}

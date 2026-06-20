import { Focusable, PanelSection, PanelSectionRow } from "@decky/ui";
import { MUTED } from "../theme";
import type { MapStorageModel } from "../hooks";

export function DetailsSection({ model }: { model: MapStorageModel }) {
  const { status, selectedPath, mountTarget, pluginVersion, isRoot, output } = model;

  const summary = [
    `Device: ${status?.device_path || selectedPath || "none"}`,
    `Mount: ${mountTarget || "not mounted"}`,
    `Service: ${status?.service_active ?? "unknown"} (${status?.service_enabled ?? "unknown"})`,
    pluginVersion ? `Plugin v${pluginVersion}${isRoot ? " · root" : ""}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <PanelSection title="Details">
      <PanelSectionRow>
        <Focusable style={{ width: "100%" }}>
          <div style={{ fontSize: "0.78em", color: MUTED, whiteSpace: "pre-wrap" }}>
            {summary}
          </div>
        </Focusable>
      </PanelSectionRow>
      {output ? (
        <PanelSectionRow>
          <Focusable style={{ width: "100%" }}>
            <div style={{ fontSize: "0.76em", color: MUTED, whiteSpace: "pre-wrap" }}>
              {output}
            </div>
          </Focusable>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

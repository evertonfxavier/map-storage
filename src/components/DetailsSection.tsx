import { Focusable, PanelSection, PanelSectionRow } from "@decky/ui";
import { MUTED } from "../theme";
import type { MapStorageModel } from "../hooks";

export function DetailsSection({ model }: { model: MapStorageModel }) {
  const { scan, enabledDrives, drives, pluginVersion, isRoot, output } = model;

  const service = scan?.service ?? {};
  const summary = [
    `Enabled: ${enabledDrives.length} of ${drives.length} drive(s)`,
    `Boot service: ${service.active ?? "unknown"} (${service.enabled ?? "unknown"})`,
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

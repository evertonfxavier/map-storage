import { ButtonItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { driveDescription } from "../lib";
import { MUTED } from "../theme";
import type { MapStorageModel } from "../hooks";

export function DrivesSection({ model }: { model: MapStorageModel }) {
  const { drives, busy, isEnabled, toggleDrive, refresh } = model;

  return (
    <PanelSection title="Your drives">
      {drives.length ? (
        drives.map((drive) => (
          <PanelSectionRow key={drive.uuid}>
            <ToggleField
              label={drive.name}
              description={driveDescription(drive)}
              checked={isEnabled(drive)}
              disabled={busy}
              onChange={(enabled) => void toggleDrive(drive, enabled)}
            />
          </PanelSectionRow>
        ))
      ) : (
        <PanelSectionRow>
          <div style={{ fontSize: "0.82em", color: MUTED }}>
            No usable drives found. System disks are hidden on purpose.
          </div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <div style={{ fontSize: "0.78em", color: MUTED }}>
          Enabled drives are mounted on every boot, before Steam starts.
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => void refresh(true)} disabled={busy}>
          Re-scan drives
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

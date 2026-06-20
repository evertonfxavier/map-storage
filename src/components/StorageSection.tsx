import { ButtonItem, Dropdown, PanelSection, PanelSectionRow } from "@decky/ui";
import { MUTED } from "../theme";
import type { MapStorageModel } from "../hooks";

export function StorageSection({ model }: { model: MapStorageModel }) {
  const {
    dropdownOptions,
    selectedPath,
    busy,
    primaryLabel,
    selectDevice,
    runConfigure,
    refreshDevices,
  } = model;

  const options = dropdownOptions.length
    ? dropdownOptions
    : [{ data: "", label: "No drives — tap Re-scan" }];

  return (
    <PanelSection title="Your storage">
      <PanelSectionRow>
        <Dropdown
          rgOptions={options}
          selectedOption={selectedPath || null}
          strDefaultLabel="Choose a drive"
          onChange={(opt) => selectDevice(String(opt?.data ?? ""))}
          disabled={busy || !dropdownOptions.length}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => void runConfigure()}
          disabled={busy || !selectedPath}
        >
          {primaryLabel}
        </ButtonItem>
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={{ fontSize: "0.78em", color: MUTED }}>
          Mounts this drive automatically in Game Mode and after SteamOS updates.
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => void refreshDevices(true)}
          disabled={busy}
        >
          Re-scan drives
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

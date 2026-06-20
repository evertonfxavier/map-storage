import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
} from "@decky/ui";
import { isTrue } from "../lib";
import type { MapStorageModel } from "../hooks";

export function AdvancedSection({ model }: { model: MapStorageModel }) {
  const {
    showAdvanced,
    setShowAdvanced,
    label,
    setLabel,
    formatOnApply,
    setFormatOnApply,
    busy,
    selectedPath,
    selectedDevice,
    runFormatOnly,
    runReapply,
    showLogs,
    loadStatus,
  } = model;

  const isSystem = isTrue(selectedDevice?.is_system);

  return (
    <PanelSection title="Advanced">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? "Hide advanced options" : "Show advanced options"}
        </ButtonItem>
      </PanelSectionRow>

      {showAdvanced ? (
        <>
          <PanelSectionRow>
            <TextField
              label="Filesystem label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              disabled={busy}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label="Format before setup"
              description="Erases all data on the selected drive."
              checked={formatOnApply}
              onChange={setFormatOnApply}
              disabled={busy}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => void runFormatOnly()}
              disabled={busy || !selectedPath || isSystem}
            >
              Format only (destructive)
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => void runReapply()} disabled={busy}>
              Re-apply after system update
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => void showLogs()} disabled={busy}>
              Show service logs
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => void loadStatus(false)}
              disabled={busy || !selectedPath}
            >
              Check status
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}
    </PanelSection>
  );
}

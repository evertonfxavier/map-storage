import {
  ButtonItem,
  ConfirmModal,
  Dropdown,
  PanelSection,
  PanelSectionRow,
  showModal,
  TextField,
} from "@decky/ui";
import { LABEL_PATTERN, formatTargetLabel } from "../lib";
import { MUTED } from "../theme";
import type { MapStorageModel } from "../hooks";

export function AdvancedSection({ model }: { model: MapStorageModel }) {
  const {
    showAdvanced,
    setShowAdvanced,
    busy,
    formatTargets,
    formatPath,
    setFormatPath,
    formatLabel,
    setFormatLabel,
    runFormat,
    runReapply,
    showLogs,
  } = model;

  const target = formatTargets.find((t) => t.path === formatPath);
  const labelValid = LABEL_PATTERN.test(formatLabel);

  const confirmFormat = () => {
    if (!target) return;
    showModal(
      <ConfirmModal
        strTitle="Erase this drive?"
        strDescription={`Everything on ${target.name} (${target.path}, ${target.size}) will be permanently erased and formatted as ext4 “${formatLabel}”.`}
        strOKButtonText="Erase and format"
        bDestructiveWarning
        onOK={() => void runFormat(target)}
      />
    );
  };

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
            <ButtonItem layout="below" onClick={() => void runReapply()} disabled={busy}>
              Re-apply and mount now
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => void showLogs()} disabled={busy}>
              Show mount logs
            </ButtonItem>
          </PanelSectionRow>

          <PanelSectionRow>
            <div style={{ fontSize: "0.8em", color: MUTED }}>
              Format a drive (erases everything on it). System disks are not listed.
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <Dropdown
              rgOptions={formatTargets.map((t) => ({
                data: t.path,
                label: formatTargetLabel(t),
              }))}
              selectedOption={formatPath || null}
              strDefaultLabel="Choose a drive to format"
              onChange={(option) => setFormatPath(String(option?.data ?? ""))}
              disabled={busy || !formatTargets.length}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label="New filesystem label"
              value={formatLabel}
              onChange={(event) => setFormatLabel(event.target.value)}
              disabled={busy}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={confirmFormat}
              disabled={busy || !target || !labelValid}
            >
              Erase, format and enable…
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}
    </PanelSection>
  );
}

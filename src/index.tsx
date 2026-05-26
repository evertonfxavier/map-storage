import {
  ButtonItem,
  Dropdown,
  PanelSection,
  PanelSectionRow,
  staticClasses,
  TextField,
  ToggleField,
} from "@decky/ui";
import {
  callable,
  definePlugin,
  toaster,
} from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaHdd } from "react-icons/fa";

type StorageDevice = {
  id: string;
  path: string;
  name: string;
  size: string;
  type: string;
  fstype: string;
  label: string;
  mountpoint: string;
  model: string;
  transport: string;
  is_system: string;
  can_format: string;
};

type PluginConfig = {
  device_path: string;
  label: string;
  format_on_apply: boolean;
};

type FixResult = {
  ok: boolean;
  label: string;
  device_path?: string;
  partition?: string;
  mount_target?: string;
  formatted?: boolean;
  logs: string[];
  errors: string[];
};

type StatusResult = {
  device_path: string;
  label: string;
  partition: string;
  mount_target: string;
  readonly_status: string;
  service_enabled: string;
  service_active: string;
  has_udev_rule: string;
  has_mount_script: string;
  has_service_file: string;
  configured_label: string;
};

const listStorageDevices = callable<[], StorageDevice[]>("list_storage_devices");
const getConfig = callable<[], PluginConfig>("get_config");
const saveConfig = callable<
  [device_path: string, label: string, format_on_apply: boolean],
  PluginConfig
>("save_config");
const formatStorage = callable<[device_path: string, label: string], FixResult>(
  "format_storage"
);
const applyStorageFix = callable<
  [device_path: string, label: string, format_drive: boolean],
  FixResult
>("apply_storage_fix");
const getStatus = callable<[device_path: string, label: string], StatusResult>(
  "get_status"
);
const getServiceLogs = callable<[lines: number], string>("get_service_logs");

function deviceLabel(dev: StorageDevice): string {
  const meta = [
    dev.transport !== "unknown" ? dev.transport : "",
    dev.model,
    dev.size,
    dev.type,
    dev.fstype || "no-fs",
    dev.label ? `label:${dev.label}` : "",
    dev.mountpoint ? `mount:${dev.mountpoint}` : "",
    dev.is_system === "true" ? "SYSTEM" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return `${dev.path} (${meta})`;
}

function Content() {
  const [devices, setDevices] = useState<StorageDevice[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [label, setLabel] = useState("SteamLibrary");
  const [formatOnApply, setFormatOnApply] = useState(false);
  const [status, setStatus] = useState<StatusResult | null>(null);
  const [output, setOutput] = useState("Select a storage device and configure.");
  const [busy, setBusy] = useState(false);

  const dropdownOptions = useMemo(
    () =>
      devices.map((dev) => ({
        data: dev.path,
        label: deviceLabel(dev),
      })),
    [devices]
  );

  const selectedDevice = devices.find((d) => d.path === selectedPath);

  const statusLines = useMemo(() => {
    if (!status) return ["Status not loaded yet."];
    return [
      `device: ${status.device_path || selectedPath || "none"}`,
      `label: ${status.label}`,
      `partition: ${status.partition || "not found"}`,
      `mount: ${status.mount_target || "not mounted"}`,
      `readonly: ${status.readonly_status}`,
      `service: ${status.service_active} (${status.service_enabled})`,
      `udev: ${status.has_udev_rule} · script: ${status.has_mount_script}`,
    ];
  }, [status, selectedPath]);

  const refreshDevices = async () => {
    setBusy(true);
    try {
      const list = await listStorageDevices();
      setDevices(list);
      if (list.length === 0) {
        setOutput("No storage devices found.");
        return;
      }
      if (!selectedPath && list[0]) {
        const first =
          list.find((d) => d.is_system !== "true" && d.can_format === "true") ??
          list[0];
        setSelectedPath(first.path);
      }
      setOutput(`Found ${list.length} storage device(s).`);
    } catch (error) {
      setOutput(`Device scan failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const loadInitialConfig = async () => {
    try {
      const cfg = await getConfig();
      if (cfg.device_path) setSelectedPath(cfg.device_path);
      if (cfg.label) setLabel(cfg.label);
      setFormatOnApply(!!cfg.format_on_apply);
    } catch (error) {
      console.log("config load failed", error);
    }
  };

  useEffect(() => {
    void loadInitialConfig();
    void refreshDevices();
  }, []);

  const persistConfig = async () => {
    await saveConfig(selectedPath, label, formatOnApply);
  };

  const loadStatus = async () => {
    if (!selectedPath) {
      toaster.toast({ title: "No device", body: "Select a storage device first." });
      return;
    }
    setBusy(true);
    try {
      await persistConfig();
      const data = await getStatus(selectedPath, label);
      setStatus(data);
      setOutput(
        data.partition
          ? `Partition ${data.partition} · mount ${data.mount_target || "none"}`
          : "Partition not found for this label/device."
      );
    } catch (error) {
      setOutput(`Status failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const runFormatOnly = async () => {
    if (!selectedPath) {
      toaster.toast({ title: "No device", body: "Select a storage device first." });
      return;
    }
    if (selectedDevice?.is_system === "true") {
      toaster.toast({
        title: "Blocked",
        body: "This device looks like system storage.",
      });
      return;
    }
    setBusy(true);
    try {
      await persistConfig();
      const result = await formatStorage(selectedPath, label);
      setOutput(formatResult(result));
      toaster.toast({
        title: result.ok ? "Formatted" : "Format failed",
        body: result.ok ? label : result.errors.join(", "),
      });
      await refreshDevices();
      await loadStatus();
    } catch (error) {
      setOutput(`Format failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const runFix = async () => {
    if (!selectedPath) {
      toaster.toast({ title: "No device", body: "Select a storage device first." });
      return;
    }
    if (formatOnApply && selectedDevice?.is_system === "true") {
      toaster.toast({
        title: "Blocked",
        body: "Cannot format a system device.",
      });
      return;
    }
    setBusy(true);
    try {
      await persistConfig();
      const result = await applyStorageFix(
        selectedPath,
        label,
        formatOnApply
      );
      setOutput(formatResult(result));
      toaster.toast({
        title: result.ok ? "Storage configured" : "Setup failed",
        body: result.ok
          ? formatOnApply
            ? "Formatted and automount enabled"
            : "Automount enabled (no format)"
          : "See output",
      });
      await loadStatus();
    } catch (error) {
      setOutput(`Setup failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const loadLogs = async () => {
    setBusy(true);
    try {
      const logs = await getServiceLogs(120);
      setOutput(logs || "No service logs found.");
    } catch (error) {
      setOutput(`Log read failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSection title="Storage devices">
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={refreshDevices} disabled={busy}>
            Rescan all storage
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Dropdown
            rgOptions={dropdownOptions}
            selectedOption={selectedPath || null}
            strDefaultLabel="Select disk or partition"
            onChange={(opt) => {
              if (opt?.data) setSelectedPath(String(opt.data));
            }}
            disabled={busy || dropdownOptions.length === 0}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Filesystem label (ext4, max 16 chars)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={busy}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Format before setup (erases all data on selected drive)"
            checked={formatOnApply}
            onChange={(checked) => setFormatOnApply(checked)}
            disabled={busy}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Actions">
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={loadStatus} disabled={busy}>
            Check status
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={runFormatOnly}
            disabled={busy || !selectedPath}
          >
            Format only (destructive)
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={runFix} disabled={busy}>
            {formatOnApply
              ? "Format + configure automount"
              : "Configure automount (no format)"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={loadLogs} disabled={busy}>
            Show service logs
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Status">
        <PanelSectionRow>
          <div style={{ fontSize: "0.8em", whiteSpace: "pre-wrap", width: "100%" }}>
            {statusLines.join("\n")}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "0.8em", whiteSpace: "pre-wrap", width: "100%" }}>
            {output}
          </div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

function formatResult(result: FixResult): string {
  const lines = [
    `ok: ${result.ok}`,
    `label: ${result.label}`,
    `device: ${result.device_path ?? "n/a"}`,
    `partition: ${result.partition ?? "n/a"}`,
    `mount: ${result.mount_target ?? "n/a"}`,
    `formatted: ${result.formatted ?? false}`,
    "",
    ...result.logs,
  ];
  if (result.errors.length > 0) {
    lines.push("", "errors:", ...result.errors);
  }
  return lines.join("\n");
}

export default definePlugin(() => {
  return {
    name: "Map Storage",
    titleView: <div className={staticClasses.Title}>Map Storage</div>,
    content: <Content />,
    icon: <FaHdd />,
    onDismount() {
      console.log("Map Storage unloading");
    },
  };
});

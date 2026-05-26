import {
  ButtonItem,
  Dropdown,
  PanelSection,
  PanelSectionRow,
  Spinner,
  staticClasses,
  TextField,
  ToggleField,
} from "@decky/ui";
import {
  callable,
  definePlugin,
  toaster,
} from "@decky/api";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FaHdd } from "react-icons/fa";

type StorageScanResult = {
  devices: StorageDevice[];
  debug: string;
  error: string;
  ok: boolean;
  count: number;
};

type StorageDevice = {
  id: string;
  path: string;
  name: string;
  size: string;
  type: string;
  fstype: string;
  label: string;
  storage_label?: string;
  mountpoint: string;
  model: string;
  transport: string;
  is_system: string;
  can_format: string;
  is_mounted?: string;
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
  storage_label?: string;
};

type ScanUiState = "idle" | "loading" | "ok" | "error";

const listStorageDevices = callable<[], string>("list_storage_devices");
const pingBackend = callable<[], Record<string, string>>("ping");
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

function storageLabelOf(dev: StorageDevice | undefined): string {
  if (!dev) return "";
  return (dev.storage_label || dev.label || "").trim();
}

function deviceLabel(dev: StorageDevice): string {
  const name = storageLabelOf(dev);
  const meta = [
    dev.size,
    dev.fstype || "no-fs",
    dev.is_mounted === "true" || dev.mountpoint ? "mounted" : "unmounted",
    dev.transport === "encrypted" ? "encrypted" : "",
    dev.type,
    dev.is_system === "true" ? "SYSTEM" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  if (name) {
    return `${name} — ${dev.path} (${meta})`;
  }
  return `${dev.path} (no label · ${meta})`;
}

function pickPreferredDevice(list: StorageDevice[]): StorageDevice | undefined {
  return (
    list.find((d) => d.transport === "steam-library" && d.type === "part") ??
    list.find((d) => d.mountpoint && d.label && d.type === "part") ??
    list.find((d) => /nvme1n1/.test(d.path) && d.type === "part" && d.label) ??
    list.find(
      (d) => storageLabelOf(d).toLowerCase() === "nvme1tb"
    ) ??
    list.find(
      (d) =>
        d.is_system !== "true" &&
        d.type === "part" &&
        (d.is_mounted === "true" || !!d.mountpoint)
    ) ??
    list.find((d) => d.is_system !== "true" && d.type === "part") ??
    list.find((d) => d.is_system !== "true") ??
    list[0]
  );
}

function parseScanResult(raw: unknown): StorageScanResult {
  let data: unknown = raw;

  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      const snippet = typeof data === "string" ? data.slice(0, 120) : String(data);
      return {
        devices: [],
        debug: "",
        error: `Invalid JSON from backend: ${snippet}`,
        ok: false,
        count: 0,
      };
    }
  }

  if (Array.isArray(data)) {
    return {
      devices: data as StorageDevice[],
      debug: "legacy list response",
      error: "",
      ok: data.length > 0,
      count: data.length,
    };
  }

  const obj = (data ?? {}) as Record<string, unknown>;
  const devices = Array.isArray(obj.devices) ? (obj.devices as StorageDevice[]) : [];

  return {
    devices,
    debug: String(obj.debug ?? ""),
    error: String(obj.error ?? ""),
    ok: Boolean(obj.ok ?? devices.length > 0),
    count: Number(obj.count ?? devices.length),
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function Content() {
  const [devices, setDevices] = useState<StorageDevice[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [label, setLabel] = useState("SteamLibrary");
  const [formatOnApply, setFormatOnApply] = useState(false);
  const [status, setStatus] = useState<StatusResult | null>(null);
  const [output, setOutput] = useState("Tap “Rescan all storage” to scan devices.");
  const [busy, setBusy] = useState(false);
  const [scanState, setScanState] = useState<ScanUiState>("idle");
  const [pluginVersion, setPluginVersion] = useState("");

  const dropdownOptions = useMemo(
    () =>
      devices.map((dev) => ({
        data: dev.path,
        label: deviceLabel(dev),
      })),
    [devices]
  );

  const selectedDevice = devices.find((d) => d.path === selectedPath);
  const selectedStorageLabel = storageLabelOf(selectedDevice) || label;

  const selectedSummary = useMemo(() => {
    if (!selectedPath) {
      return "No device selected — run Rescan and pick a partition.";
    }
    const dev = selectedDevice;
    const storageName = storageLabelOf(dev) || "(no label detected)";
    const lines = [
      `Storage label: ${storageName}`,
      `Device: ${selectedPath}`,
    ];
    if (dev) {
      lines.push(
        `Size: ${dev.size}`,
        `Filesystem: ${dev.fstype || "unknown"}`,
        dev.mountpoint ? `Mount: ${dev.mountpoint}` : "Mount: not mounted"
      );
      if (dev.label && dev.storage_label && dev.label !== dev.storage_label) {
        lines.push(`Filesystem LABEL: ${dev.label}`);
      }
    }
    return lines.join("\n");
  }, [selectedPath, selectedDevice]);

  const scanBanner = useMemo(() => {
    switch (scanState) {
      case "loading":
        return "Scanning storage devices…";
      case "ok":
        return `Scan OK — ${devices.length} device(s) found`;
      case "error":
        return "Scan failed — see details below";
      default:
        return devices.length
          ? `${devices.length} device(s) in list`
          : "No devices loaded yet";
    }
  }, [scanState, devices.length]);

  const statusLines = useMemo(() => {
    if (!status) {
      if (selectedPath) {
        return [
          `storage label: ${selectedStorageLabel || "(none)"}`,
          `device: ${selectedPath}`,
          "Tap “Check status” for mount and service details.",
        ];
      }
      return ["Status not loaded yet."];
    }
    const displayLabel =
      status.storage_label || status.label || selectedStorageLabel || "(none)";
    return [
      `storage label: ${displayLabel}`,
      `device: ${status.device_path || selectedPath || "none"}`,
      `configured label: ${status.label}`,
      `partition: ${status.partition || "not found"}`,
      `mount: ${status.mount_target || "not mounted"}`,
      `readonly: ${status.readonly_status}`,
      `service: ${status.service_active} (${status.service_enabled})`,
      `udev: ${status.has_udev_rule} · script: ${status.has_mount_script}`,
    ];
  }, [status, selectedPath, selectedStorageLabel]);

  const refreshDevices = useCallback(async (fromUser = false, savedPath = "") => {
    setBusy(true);
    setScanState("loading");
    setOutput("Scanning…");

    if (fromUser) {
      toaster.toast({ title: "Scanning", body: "Looking for storage devices…" });
    }

    try {
      const raw = await listStorageDevices();
      const scan = parseScanResult(raw);
      const list = scan.devices;

      setDevices(list);

      if (list.length === 0) {
        setScanState("error");
        const lines = [
          scan.error || "No storage devices found.",
          "",
          scan.debug ? `Debug: ${scan.debug}` : "Debug: (empty)",
          "",
          "If NVMe1TB appears in Steam Settings, the label is likely NVMe1TB.",
        ];
        setOutput(lines.join("\n"));
        toaster.toast({
          title: "No devices",
          body: scan.error || "Scan returned an empty list",
        });
        return;
      }

      setScanState("ok");

      const keepPath = savedPath || selectedPath;
      const stillValid = list.find((d) => d.path === keepPath);
      const preferred = stillValid ?? pickPreferredDevice(list);

      if (preferred) {
        setSelectedPath(preferred.path);
        const detected = storageLabelOf(preferred);
        if (detected) {
          setLabel(detected);
        } else if (preferred.label) {
          setLabel(preferred.label);
        }
      }

      setOutput(
        [`Found ${list.length} device(s).`, scan.debug ? `Debug: ${scan.debug}` : ""]
          .filter(Boolean)
          .join("\n")
      );

      toaster.toast({
        title: "Scan complete",
        body: `${list.length} device(s) found`,
      });
    } catch (error) {
      const msg = errorMessage(error);
      setScanState("error");
      setDevices([]);
      setOutput(`Scan failed:\n${msg}\n\nIs the plugin backend running?`);
      toaster.toast({ title: "Scan error", body: msg });
      console.error("[map-storage] scan failed", error);
    } finally {
      setBusy(false);
    }
  }, [selectedPath]);

  const checkBackend = async () => {
    try {
      const pong = await pingBackend();
      if (pong?.version) setPluginVersion(pong.version);
      if (pong?.status !== "ok") {
        throw new Error("Backend ping failed");
      }
    } catch (error) {
      const msg = errorMessage(error);
      setScanState("error");
      setOutput(`Backend not reachable:\n${msg}`);
      toaster.toast({ title: "Backend error", body: msg });
    }
  };

  useEffect(() => {
    void (async () => {
      await checkBackend();
      let savedPath = "";
      try {
        const cfg = await getConfig();
        if (cfg.device_path) {
          savedPath = cfg.device_path;
          setSelectedPath(cfg.device_path);
        }
        if (cfg.label) setLabel(cfg.label);
        setFormatOnApply(!!cfg.format_on_apply);
      } catch (error) {
        console.error("[map-storage] config load failed", error);
      }
      await refreshDevices(false, savedPath);
    })();
  }, [refreshDevices]);

  const persistConfig = async () => {
    await saveConfig(selectedPath, label, formatOnApply);
  };

  const loadStatus = async () => {
    if (!selectedPath) {
      toaster.toast({ title: "No device", body: "Select a storage device first." });
      return;
    }
    setBusy(true);
    setOutput("Checking status…");
    try {
      await persistConfig();
      const data = await getStatus(selectedPath, label);
      setStatus(data);
      setOutput(
        data.partition
          ? `Partition ${data.partition} · mount ${data.mount_target || "none"}`
          : "Partition not found for this label/device."
      );
      toaster.toast({ title: "Status", body: data.partition ? "Found" : "Not found" });
    } catch (error) {
      const msg = errorMessage(error);
      setOutput(`Status failed:\n${msg}`);
      toaster.toast({ title: "Status error", body: msg });
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
    setOutput("Formatting…");
    try {
      await persistConfig();
      const result = await formatStorage(selectedPath, label);
      setOutput(formatResult(result));
      toaster.toast({
        title: result.ok ? "Formatted" : "Format failed",
        body: result.ok ? label : result.errors.join(", ") || "Failed",
      });
      await refreshDevices(false);
      await loadStatus();
    } catch (error) {
      const msg = errorMessage(error);
      setOutput(`Format failed:\n${msg}`);
      toaster.toast({ title: "Format error", body: msg });
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
    if (!formatOnApply && selectedDevice?.type === "disk") {
      toaster.toast({
        title: "Select a partition",
        body: "Pick a partition (e.g. nvme1n1p1), not the whole disk.",
      });
      return;
    }
    if (selectedDevice?.transport === "encrypted") {
      toaster.toast({
        title: "Encrypted volume",
        body: "Unlock the drive in Desktop Mode first.",
      });
      return;
    }
    setBusy(true);
    setOutput("Applying automount setup…");
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
          : result.errors[0] || "See output",
      });
      await loadStatus();
    } catch (error) {
      const msg = errorMessage(error);
      setOutput(`Setup failed:\n${msg}`);
      toaster.toast({ title: "Setup error", body: msg });
    } finally {
      setBusy(false);
    }
  };

  const loadLogs = async () => {
    setBusy(true);
    setOutput("Loading logs…");
    try {
      const logs = await getServiceLogs(120);
      setOutput(logs || "No service logs found.");
      toaster.toast({ title: "Logs", body: "Loaded service logs" });
    } catch (error) {
      const msg = errorMessage(error);
      setOutput(`Log read failed:\n${msg}`);
      toaster.toast({ title: "Log error", body: msg });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSection title="Storage devices">
        {pluginVersion ? (
          <PanelSectionRow>
            <div style={{ fontSize: "0.75em", opacity: 0.8 }}>
              Plugin v{pluginVersion}
            </div>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <div
            style={{
              fontSize: "0.85em",
              fontWeight: 600,
              color: scanState === "error" ? "#ff6b6b" : undefined,
            }}
          >
            {scanBanner}
          </div>
        </PanelSectionRow>
        {busy ? (
          <PanelSectionRow>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Spinner />
              <span style={{ fontSize: "0.85em" }}>Please wait…</span>
            </div>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => void refreshDevices(true)}
            disabled={busy}
          >
            {busy ? "Scanning…" : "Rescan all storage"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Dropdown
            rgOptions={
              dropdownOptions.length > 0
                ? dropdownOptions
                : [{ data: "", label: "(no devices — run Rescan)" }]
            }
            selectedOption={selectedPath || null}
            strDefaultLabel={
              dropdownOptions.length > 0
                ? "Select disk or partition"
                : "No devices — tap Rescan"
            }
            onChange={(opt) => {
              const path = String(opt?.data ?? "");
              if (!path) return;
              setSelectedPath(path);
              const dev = devices.find((d) => d.path === path);
              const detected = storageLabelOf(dev);
              if (detected) setLabel(detected);
              else if (dev?.label) setLabel(dev.label);
            }}
            disabled={busy || dropdownOptions.length === 0}
          />
        </PanelSectionRow>
        {selectedPath ? (
          <PanelSectionRow>
            <div
              style={{
                fontSize: "0.8em",
                whiteSpace: "pre-wrap",
                width: "100%",
                opacity: 0.95,
              }}
            >
              {selectedSummary}
            </div>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <TextField
            label={
              selectedStorageLabel
                ? `Filesystem label (detected: ${selectedStorageLabel})`
                : "Filesystem label (ext4, max 16 chars)"
            }
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
          <ButtonItem layout="below" onClick={() => void loadStatus()} disabled={busy}>
            Check status
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => void runFormatOnly()}
            disabled={busy || !selectedPath}
          >
            Format only (destructive)
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void runFix()} disabled={busy}>
            {formatOnApply
              ? "Format + configure automount"
              : "Configure automount (no format)"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void loadLogs()} disabled={busy}>
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

import { toaster } from "@decky/api";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyStorageFix,
  formatStorage,
  getConfig,
  getServiceLogs,
  getStatus,
  listStorageDevices,
  pingBackend,
  reapplyNow,
  saveConfig,
} from "../api";
import {
  deviceOptionLabel,
  errorMessage,
  fixResultText,
  isTrue,
  parseScanResult,
  pickPreferredDevice,
  storageLabelOf,
} from "../lib";
import type { StatusResult, StorageDevice } from "../model";

export function useMapStorage() {
  const [devices, setDevices] = useState<StorageDevice[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [label, setLabel] = useState("SteamLibrary");
  const [formatOnApply, setFormatOnApply] = useState(false);
  const [status, setStatus] = useState<StatusResult | null>(null);
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState("");
  const [pluginVersion, setPluginVersion] = useState("");
  const [isRoot, setIsRoot] = useState<boolean | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const selectedPathRef = useRef(selectedPath);
  useEffect(() => {
    selectedPathRef.current = selectedPath;
  }, [selectedPath]);

  const selectedDevice = devices.find((d) => d.path === selectedPath);
  const storageName = storageLabelOf(selectedDevice) || label;
  const mountTarget = status?.mount_target || selectedDevice?.mountpoint || "";
  const isMounted = !!mountTarget;
  const serviceActive = status?.service_active === "active";

  const dropdownOptions = useMemo(
    () =>
      devices.map((device) => ({
        data: device.path,
        label: deviceOptionLabel(device),
      })),
    [devices]
  );

  const notify = useCallback((title: string, body: string) => {
    toaster.toast({ title, body });
  }, []);

  const loadStatus = useCallback(
    async (silent = false) => {
      const path = selectedPathRef.current;
      if (!path) return;
      try {
        await saveConfig(path, label, formatOnApply);
        const data = await getStatus(path, label);
        setStatus(data);
        if (!silent) notify("Status", data.partition ? "Found" : "Not found");
      } catch (error) {
        if (!silent) notify("Status error", errorMessage(error));
      }
    },
    [label, formatOnApply, notify]
  );

  const refreshDevices = useCallback(
    async (fromUser = false, savedPath = "") => {
      setBusy(true);
      setScanError("");
      try {
        const scan = parseScanResult(await listStorageDevices());
        setDevices(scan.devices);

        if (!scan.devices.length) {
          setScanError(scan.error || "No storage devices found.");
          if (fromUser) notify("No devices", scan.error || "Empty list");
          return;
        }

        const keepPath = savedPath || selectedPathRef.current;
        const stillValid = scan.devices.find((d) => d.path === keepPath);
        const chosen = stillValid ?? pickPreferredDevice(scan.devices);
        if (chosen) {
          setSelectedPath(chosen.path);
          const detected = storageLabelOf(chosen);
          if (!stillValid && detected) setLabel(detected);
        }
        if (fromUser) notify("Scan complete", `${scan.devices.length} device(s)`);
      } catch (error) {
        setScanError(errorMessage(error));
        setDevices([]);
        if (fromUser) notify("Scan error", errorMessage(error));
      } finally {
        setBusy(false);
      }
    },
    [notify]
  );

  useEffect(() => {
    void (async () => {
      try {
        const pong = await pingBackend();
        if (pong?.version) setPluginVersion(pong.version);
        if (typeof pong?.is_root === "string") setIsRoot(pong.is_root === "true");
      } catch (error) {
        setScanError(`Backend not reachable: ${errorMessage(error)}`);
      }

      let savedPath = "";
      try {
        const cfg = await getConfig();
        if (cfg.device_path) {
          savedPath = cfg.device_path;
          setSelectedPath(cfg.device_path);
        }
        if (cfg.label) setLabel(cfg.label);
        setFormatOnApply(!!cfg.format_on_apply);
      } catch {
        setFormatOnApply(false);
      }

      await refreshDevices(false, savedPath);
      await loadStatus(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectDevice = useCallback(
    (path: string) => {
      if (!path) return;
      setSelectedPath(path);
      const detected = storageLabelOf(devices.find((d) => d.path === path));
      if (detected) setLabel(detected);
    },
    [devices]
  );

  const runConfigure = useCallback(async () => {
    if (!selectedPath) return notify("No device", "Select a storage drive first.");
    if (formatOnApply && isTrue(selectedDevice?.is_system)) {
      return notify("Blocked", "Cannot format a system device.");
    }
    if (!formatOnApply && selectedDevice?.type === "disk") {
      return notify("Select a partition", "Pick a partition, not the whole disk.");
    }
    if (selectedDevice?.transport === "encrypted") {
      return notify("Encrypted volume", "Unlock it in Desktop Mode first.");
    }

    setBusy(true);
    setOutput("Enabling automount…");
    try {
      await saveConfig(selectedPath, label, formatOnApply);
      const result = await applyStorageFix(selectedPath, label, formatOnApply);
      setOutput(fixResultText(result));
      notify(
        result.ok ? "Automount enabled" : "Setup failed",
        result.ok ? mountTarget || label : result.errors[0] || "See details"
      );
      await loadStatus(true);
    } catch (error) {
      setOutput(`Setup failed:\n${errorMessage(error)}`);
      notify("Setup error", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }, [selectedPath, formatOnApply, selectedDevice, label, mountTarget, notify, loadStatus]);

  const runFormatOnly = useCallback(async () => {
    if (!selectedPath) return notify("No device", "Select a storage drive first.");
    if (isTrue(selectedDevice?.is_system)) {
      return notify("Blocked", "This device looks like system storage.");
    }
    setBusy(true);
    setOutput("Formatting…");
    try {
      await saveConfig(selectedPath, label, formatOnApply);
      const result = await formatStorage(selectedPath, label);
      setOutput(fixResultText(result));
      notify(result.ok ? "Formatted" : "Format failed", result.ok ? label : "Failed");
      await refreshDevices(false);
      await loadStatus(true);
    } catch (error) {
      setOutput(`Format failed:\n${errorMessage(error)}`);
      notify("Format error", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }, [selectedPath, selectedDevice, label, formatOnApply, notify, refreshDevices, loadStatus]);

  const runReapply = useCallback(async () => {
    setBusy(true);
    setOutput("Re-applying saved automount…");
    try {
      const result = await reapplyNow();
      setOutput(fixResultText(result));
      notify(
        result.ok ? "Re-applied" : "Re-apply incomplete",
        result.ok ? `Mounted at ${result.mount_target}` : result.errors[0] || "See details"
      );
      await loadStatus(true);
    } catch (error) {
      setOutput(`Re-apply failed:\n${errorMessage(error)}`);
      notify("Re-apply error", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }, [notify, loadStatus]);

  const showLogs = useCallback(async () => {
    setBusy(true);
    setOutput("Loading logs…");
    try {
      setOutput((await getServiceLogs(120)) || "No service logs found.");
    } catch (error) {
      setOutput(`Log read failed:\n${errorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const primaryLabel = busy
    ? "Working…"
    : formatOnApply
    ? "Format + enable automount"
    : "Enable automount";

  return {
    devices,
    selectedPath,
    selectedDevice,
    label,
    formatOnApply,
    status,
    output,
    busy,
    scanError,
    pluginVersion,
    isRoot,
    showAdvanced,
    storageName,
    mountTarget,
    isMounted,
    serviceActive,
    dropdownOptions,
    primaryLabel,
    setLabel,
    setFormatOnApply,
    setShowAdvanced,
    selectDevice,
    refreshDevices,
    runConfigure,
    runFormatOnly,
    runReapply,
    showLogs,
    loadStatus,
  };
}

export type MapStorageModel = ReturnType<typeof useMapStorage>;

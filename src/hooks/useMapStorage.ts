import { toaster } from "@decky/api";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  formatStorage,
  getServiceLogs,
  listStorageDevices,
  pingBackend,
  reapplyNow,
  setDriveEnabled,
} from "../api";
import { actionText, errorMessage, parseScanResult } from "../lib";
import type { ActionResult, Drive, FormatTarget, ScanResult } from "../model";

export function useMapStorage() {
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(true);
  const [scanError, setScanError] = useState("");
  const [pluginVersion, setPluginVersion] = useState("");
  const [isRoot, setIsRoot] = useState<boolean | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [formatPath, setFormatPath] = useState("");
  const [formatLabel, setFormatLabel] = useState("SteamLibrary");

  const drives = scan?.drives ?? [];
  const formatTargets = scan?.format_targets ?? [];
  const enabledDrives = useMemo(() => drives.filter((d) => d.enabled), [drives]);
  const attentionDrives = useMemo(
    () => enabledDrives.filter((d) => !d.present || !d.mounted),
    [enabledDrives]
  );

  const notify = useCallback((title: string, body: string) => {
    toaster.toast({ title, body });
  }, []);

  const loadScan = useCallback(async () => {
    try {
      const result = parseScanResult(await listStorageDevices());
      setScan(result);
      setScanError(result.ok ? "" : result.error || "Scan failed");
      setFormatPath((current) =>
        result.format_targets.some((t) => t.path === current) ? current : ""
      );
    } catch (error) {
      setScanError(errorMessage(error));
    }
  }, []);

  const refresh = useCallback(
    async (fromUser = false) => {
      setBusy(true);
      await loadScan();
      setBusy(false);
      if (fromUser) notify("Drives rescanned", "List updated.");
    },
    [loadScan, notify]
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
      await loadScan();
      setBusy(false);
    })();
  }, [loadScan]);

  const runAction = useCallback(
    async (
      working: string,
      action: () => Promise<ActionResult>,
      success: (result: ActionResult) => string,
      failure: string
    ) => {
      setBusy(true);
      setOutput(working);
      try {
        const result = await action();
        setOutput(actionText(result));
        if (result.ok) notify("Map Storage", success(result));
        else notify(failure, result.errors?.[0] || "See details");
      } catch (error) {
        setOutput(`${failure}:\n${errorMessage(error)}`);
        notify(failure, errorMessage(error));
      }
      await loadScan();
      setBusy(false);
    },
    [loadScan, notify]
  );

  const toggleDrive = useCallback(
    async (drive: Drive, enabled: boolean) => {
      setPending((current) => ({ ...current, [drive.uuid]: enabled }));
      await runAction(
        enabled ? `Enabling ${drive.name}…` : `Disabling ${drive.name}…`,
        () => setDriveEnabled(drive.uuid, enabled),
        (result) =>
          enabled
            ? `${drive.name} mounted at ${result.mount_target || "?"}`
            : `${drive.name} disabled`,
        enabled ? "Could not enable" : "Could not disable"
      );
      setPending((current) => {
        const next = { ...current };
        delete next[drive.uuid];
        return next;
      });
    },
    [runAction]
  );

  const runReapply = useCallback(
    () =>
      runAction(
        "Re-applying saved drives…",
        reapplyNow,
        () => "Automount re-applied",
        "Re-apply incomplete"
      ),
    [runAction]
  );

  const runFormat = useCallback(
    (target: FormatTarget) =>
      runAction(
        `Formatting ${target.path}…`,
        () => formatStorage(target.path, target.fingerprint, formatLabel, true),
        (result) => `${result.label ?? formatLabel} ready at ${result.mount_target || "?"}`,
        "Format failed"
      ),
    [runAction, formatLabel]
  );

  const showLogs = useCallback(async () => {
    setBusy(true);
    setOutput("Loading logs…");
    try {
      setOutput((await getServiceLogs(120)) || "No mount logs yet.");
    } catch (error) {
      setOutput(`Log read failed:\n${errorMessage(error)}`);
    }
    setBusy(false);
  }, []);

  const isEnabled = useCallback(
    (drive: Drive) => pending[drive.uuid] ?? drive.enabled,
    [pending]
  );

  return {
    scan,
    drives,
    formatTargets,
    enabledDrives,
    attentionDrives,
    output,
    busy,
    scanError,
    pluginVersion,
    isRoot,
    showAdvanced,
    formatPath,
    formatLabel,
    isEnabled,
    setShowAdvanced,
    setFormatPath,
    setFormatLabel,
    refresh,
    toggleDrive,
    runReapply,
    runFormat,
    showLogs,
  };
}

export type MapStorageModel = ReturnType<typeof useMapStorage>;

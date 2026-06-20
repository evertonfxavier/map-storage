import type { FixResult, StorageDevice, StorageScanResult } from "../model";

export const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

export const parseScanResult = (raw: unknown): StorageScanResult => {
  let data: unknown = raw;

  if (typeof data === "string") {
    const snippet = data.slice(0, 120);
    try {
      data = JSON.parse(data);
    } catch {
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
    const devices = data as StorageDevice[];
    return {
      devices,
      debug: "legacy list",
      error: "",
      ok: devices.length > 0,
      count: devices.length,
    };
  }

  const obj = (data ?? {}) as Record<string, unknown>;
  const devices = Array.isArray(obj.devices)
    ? (obj.devices as StorageDevice[])
    : [];

  return {
    devices,
    debug: String(obj.debug ?? ""),
    error: String(obj.error ?? ""),
    ok: Boolean(obj.ok ?? devices.length > 0),
    count: Number(obj.count ?? devices.length),
  };
};

export const fixResultText = (result: FixResult): string => {
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
  if (result.errors.length) {
    lines.push("", "errors:", ...result.errors);
  }
  return lines.join("\n");
};

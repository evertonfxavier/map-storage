import type { ActionResult, ScanResult } from "../model";

export const errorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

const emptyScan = (error: string): ScanResult => ({
  ok: false,
  error,
  debug: "",
  count: 0,
  os_known: false,
  drives: [],
  format_targets: [],
  service: {},
});

export const parseScanResult = (raw: unknown): ScanResult => {
  let data: unknown = raw;

  if (typeof data === "string") {
    const snippet = data.slice(0, 120);
    try {
      data = JSON.parse(data);
    } catch {
      return emptyScan(`Invalid JSON from backend: ${snippet}`);
    }
  }

  if (!data || typeof data !== "object") {
    return emptyScan("Empty response from backend");
  }

  const obj = data as Partial<ScanResult>;
  return {
    ok: Boolean(obj.ok),
    error: String(obj.error ?? ""),
    debug: String(obj.debug ?? ""),
    count: Number(obj.count ?? 0),
    os_known: Boolean(obj.os_known),
    drives: Array.isArray(obj.drives) ? obj.drives : [],
    format_targets: Array.isArray(obj.format_targets) ? obj.format_targets : [],
    service: obj.service ?? {},
  };
};

export const actionText = (result: ActionResult): string => {
  const lines = [`ok: ${result.ok}`, ...(result.logs ?? [])];
  if (result.errors?.length) {
    lines.push("", "errors:", ...result.errors);
  }
  return lines.join("\n");
};

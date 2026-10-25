import { callable } from "@decky/api";
import type { ActionResult } from "../model";

export const listStorageDevices = callable<[], string>("list_storage_devices");

export const pingBackend = callable<[], Record<string, string>>("ping");

export const setDriveEnabled = callable<
  [uuid: string, enabled: boolean],
  ActionResult
>("set_drive_enabled");

export const formatStorage = callable<
  [device_path: string, fingerprint: string, label: string, enable: boolean],
  ActionResult
>("format_storage");

export const reapplyNow = callable<[], ActionResult>("reapply_now");

export const getServiceLogs = callable<[lines: number], string>(
  "get_service_logs"
);

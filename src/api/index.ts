import { callable } from "@decky/api";
import type { FixResult, PluginConfig, StatusResult } from "../model";

export const listStorageDevices = callable<[], string>("list_storage_devices");

export const pingBackend = callable<[], Record<string, string>>("ping");

export const getConfig = callable<[], PluginConfig>("get_config");

export const saveConfig = callable<
  [device_path: string, label: string, format_on_apply: boolean],
  PluginConfig
>("save_config");

export const formatStorage = callable<
  [device_path: string, label: string],
  FixResult
>("format_storage");

export const applyStorageFix = callable<
  [device_path: string, label: string, format_drive: boolean],
  FixResult
>("apply_storage_fix");

export const getStatus = callable<
  [device_path: string, label: string],
  StatusResult
>("get_status");

export const getServiceLogs = callable<[lines: number], string>(
  "get_service_logs"
);

export const reapplyNow = callable<[], FixResult>("reapply_now");

export type StorageDevice = {
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
  is_expansion?: string;
};

export type StorageScanResult = {
  devices: StorageDevice[];
  debug: string;
  error: string;
  ok: boolean;
  count: number;
};

export type PluginConfig = {
  device_path: string;
  label: string;
  format_on_apply: boolean;
};

export type FixResult = {
  ok: boolean;
  label: string;
  device_path?: string;
  partition?: string;
  mount_target?: string;
  formatted?: boolean;
  logs: string[];
  errors: string[];
};

export type StatusResult = {
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

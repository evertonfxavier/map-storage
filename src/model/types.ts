export type Drive = {
  uuid: string;
  name: string;
  label: string;
  size: string;
  fstype: string;
  path: string;
  model: string;
  transport: string;
  mountpoint: string;
  mounted: boolean;
  enabled: boolean;
  present: boolean;
};

export type FormatTarget = {
  path: string;
  fingerprint: string;
  type: string;
  name: string;
  size: string;
  fstype: string;
  label: string;
  model: string;
  mounted: boolean;
};

export type ServiceState = {
  enabled: string;
  active: string;
  has_udev_rule: boolean;
  has_helper: boolean;
  has_unit: boolean;
};

export type ScanResult = {
  ok: boolean;
  error: string;
  debug: string;
  count: number;
  os_known: boolean;
  drives: Drive[];
  format_targets: FormatTarget[];
  service: Partial<ServiceState>;
};

export type ActionResult = {
  ok: boolean;
  logs: string[];
  errors: string[];
  label?: string;
  uuid?: string;
  enabled?: boolean;
  partition?: string;
  mount_target?: string;
};

import type { StorageDevice } from "../model";

export const isTrue = (value?: string) => value === "true";

export const storageLabelOf = (device?: StorageDevice): string =>
  device ? (device.storage_label || device.label || "").trim() : "";

export const isMountedDevice = (device?: StorageDevice): boolean =>
  !!device && (isTrue(device.is_mounted) || !!device.mountpoint);

export const deviceOptionLabel = (device: StorageDevice): string => {
  const name = storageLabelOf(device) || device.path;
  const tags = [
    device.size,
    device.fstype || "no-fs",
    isMountedDevice(device) ? "mounted" : "unmounted",
    isTrue(device.is_expansion) ? "EXPANSION" : "",
    isTrue(device.is_system) ? "SYSTEM" : "",
    device.transport === "encrypted" ? "encrypted" : "",
  ].filter(Boolean);
  return `${name} — ${tags.join(" · ")}`;
};

export const pickPreferredDevice = (
  devices: StorageDevice[]
): StorageDevice | undefined => {
  const isLibrary = (device: StorageDevice) =>
    storageLabelOf(device).toLowerCase() === "nvme1tb";
  const isPart = (device: StorageDevice) => device.type === "part";

  return (
    devices.find((d) => isLibrary(d) && isPart(d)) ??
    devices.find((d) => d.transport === "steam-library" && isPart(d)) ??
    devices.find((d) => isTrue(d.is_expansion) && isPart(d)) ??
    devices.find((d) => d.mountpoint?.startsWith("/run/media/") && isPart(d)) ??
    devices.find((d) => !isTrue(d.is_system) && isPart(d) && isMountedDevice(d)) ??
    devices.find((d) => !isTrue(d.is_system) && isPart(d)) ??
    devices.find((d) => !isTrue(d.is_system)) ??
    devices[0]
  );
};

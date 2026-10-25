import type { Drive, FormatTarget } from "../model";

export const LABEL_PATTERN = /^[A-Za-z0-9_-]{1,16}$/;

export const driveDescription = (drive: Drive): string => {
  if (!drive.present) return "Not connected";
  const state = drive.mounted
    ? `mounted at ${drive.mountpoint}`
    : "not mounted";
  return [drive.transport.toUpperCase(), drive.size, drive.fstype, state]
    .filter(Boolean)
    .join(" · ");
};

export const formatTargetLabel = (target: FormatTarget): string => {
  const kind = target.type === "disk" ? "whole disk" : "partition";
  const content = target.fstype || "blank";
  return `${target.name} — ${kind} · ${target.size} · ${content} · ${target.path}`;
};

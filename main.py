import json
import os
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import decky

UDEV_RULE_PATH = "/etc/udev/rules.d/99-map-storage-automount.rules"
MOUNT_SCRIPT_PATH = "/usr/local/bin/map-storage-mount.sh"
SERVICE_PATH = "/etc/systemd/system/map-storage-automount.service"
LEGACY_SERVICE_PATH = "/etc/systemd/system/mount-nvme1tb.service"
CONFIG_PATH = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "config.json")

LABEL_MAX_LEN = 16
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

UDEV_RULE_TEMPLATE = """# map-storage automount for label "{label}" (any block device)
SUBSYSTEM!="block", GOTO="map_storage_automount_end"
ENV{{ID_FS_USAGE}}!="filesystem", GOTO="map_storage_automount_end"
ENV{{ID_FS_LABEL}}!="{label}", GOTO="map_storage_automount_end"

ACTION=="add",    RUN+="/bin/systemd-run --no-block --collect /usr/lib/hwsupport/block-device-event.sh add %k"
ACTION=="remove", RUN+="/bin/systemd-run --no-block --collect /usr/lib/hwsupport/block-device-event.sh remove %k"

LABEL="map_storage_automount_end"
"""

# Block devices we list / allow (disks and partitions)
DEVICE_PATH_PATTERN = re.compile(
    r"^/dev/(?:"
    r"nvme\d+n\d+(?:p\d+)?|"           # NVMe
    r"sd[a-z]+\d*|mmcblk\d+(?:p\d+)?|"  # USB/SATA/SD
    r"vd[a-z]+\d*|hd[a-z]+\d*"           # VirtIO / legacy IDE
    r")$"
)

SKIP_DEVICE_PREFIXES = (
    "loop",
    "ram",
    "zram",
    "sr",
    "fd",
    "dm-",
    "md",
    "nbd",
    "rbd",
)
SKIP_DEVICE_TYPES = frozenset({"rom", "loop"})

MOUNT_SCRIPT_TEMPLATE = """#!/bin/bash
set -e

LABEL="{label}"
MAX_RETRIES=10
RETRY_DELAY=2
DECK_USER="{deck_user}"

for i in $(seq 1 $MAX_RETRIES); do
    PARTITION=$(blkid -L "$LABEL" 2>/dev/null || echo "")

    if [[ -z "$PARTITION" ]]; then
        echo "map-storage-mount[$i/$MAX_RETRIES]: partition not found, waiting..."
        sleep $RETRY_DELAY
        continue
    fi

    if findmnt -no TARGET "$PARTITION" >/dev/null 2>&1; then
        MOUNT_AT=$(findmnt -no TARGET "$PARTITION")
        chown 1000:1000 "$MOUNT_AT" 2>/dev/null || true
        echo "map-storage-mount: already mounted at $MOUNT_AT"
        exit 0
    fi

    if ! pidof udisksd >/dev/null 2>&1; then
        echo "map-storage-mount[$i/$MAX_RETRIES]: udisksd not ready, waiting..."
        sleep $RETRY_DELAY
        continue
    fi

    if sudo -u "$DECK_USER" udisksctl mount -b "$PARTITION" --no-user-interaction >/dev/null 2>&1; then
        sleep 1
        MOUNT_AT=$(findmnt -no TARGET "$PARTITION" 2>/dev/null || echo "")
        if [[ -n "$MOUNT_AT" ]]; then
            chown 1000:1000 "$MOUNT_AT" 2>/dev/null || true
            echo "map-storage-mount: mounted at $MOUNT_AT"
        fi
        exit 0
    fi

    sleep $RETRY_DELAY
done

PARTITION=$(blkid -L "$LABEL" 2>/dev/null || echo "")
if [[ -n "$PARTITION" ]]; then
    MOUNT_POINT="/run/media/$DECK_USER/$LABEL"
    mkdir -p "$MOUNT_POINT"
    mount -o rw,noatime "$PARTITION" "$MOUNT_POINT"
    chown 1000:1000 "$MOUNT_POINT"
    chmod 755 "$MOUNT_POINT"
    echo "map-storage-mount: fallback mounted at $MOUNT_POINT"
    exit 0
fi

echo "map-storage-mount: failed"
exit 1
"""

SERVICE_TEMPLATE = """[Unit]
Description=map-storage automount ({label}) via udisks2
After=udisks2.service multi-user.target
Wants=udisks2.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart={mount_script}
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


class Plugin:
    def _run(self, command: str, check: bool = False) -> subprocess.CompletedProcess:
        decky.logger.info("exec: %s", command)
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or command)
        return result

    def _write_file(self, path: str, content: str, mode: int = 0o644) -> None:
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
        os.chmod(path, mode)

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.isfile(CONFIG_PATH):
            return {
                "device_path": "",
                "label": "SteamLibrary",
                "format_on_apply": False,
            }
        with open(CONFIG_PATH, encoding="utf-8") as file:
            return json.load(file)

    def _save_config(self, config: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=2)

    def _validate_label(self, label: str) -> str:
        label = (label or "").strip()
        if not label or len(label) > LABEL_MAX_LEN:
            raise RuntimeError(
                f"label must be 1-{LABEL_MAX_LEN} chars (letters, numbers, _ or -)"
            )
        if not LABEL_PATTERN.match(label):
            raise RuntimeError("invalid label characters")
        return label

    def _validate_device_path(self, device_path: str) -> str:
        device_path = (device_path or "").strip()
        if not DEVICE_PATH_PATTERN.match(device_path):
            raise RuntimeError(f"unsupported or invalid device path: {device_path}")
        return device_path

    def _should_skip_block(self, name: str, entry_type: str) -> bool:
        if entry_type in SKIP_DEVICE_TYPES:
            return True
        return any(name.startswith(prefix) for prefix in SKIP_DEVICE_PREFIXES)

    def _is_partition_path(self, device_path: str) -> bool:
        return bool(
            re.search(
                r"(?:nvme\d+n\d+p\d+|mmcblk\d+p\d+|(?:sd|vd|hd)[a-z]+\d+)$",
                device_path,
            )
        )

    def _disk_from_path(self, device_path: str) -> str:
        device_path = self._validate_device_path(device_path)
        if self._is_partition_path(device_path):
            if "nvme" in device_path or "mmcblk" in device_path:
                return re.sub(r"p\d+$", "", device_path)
            return re.sub(r"\d+$", "", device_path)
        return device_path

    def _root_mount_sources(self) -> List[str]:
        result = self._run("findmnt -no SOURCE / /home 2>/dev/null || true")
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _is_system_device(self, path: str, mountpoint: str) -> bool:
        critical = ("/", "/home", "/var", "/usr", "/boot", "/etc")

        if not mountpoint:
            mountpoint = self._run(
                f"findmnt -no TARGET {shlex.quote(path)} 2>/dev/null || true"
            ).stdout.strip()

        # User library mounts (udisks / Steam) are never "system" for our UI
        if mountpoint.lower().startswith("/run/media/"):
            return False

        if mountpoint in critical:
            return True

        roots = self._root_mount_sources()
        if path in roots:
            return True

        for root in roots:
            if path == root:
                return True
        return False

    def _block_path(self, name: str, block: Dict[str, Any]) -> str:
        path = block.get("path") or block.get("kname") or ""
        if path and not path.startswith("/dev/"):
            path = f"/dev/{path}"
        if not path and name:
            path = f"/dev/{name}"
        return path

    def _lsblk_payload(self) -> Tuple[Optional[Dict[str, Any]], str]:
        """Try lsblk with decreasing column sets (SteamOS util-linux varies)."""
        column_sets = (
            "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,MODEL,TRAN,MOUNTPOINT,HOTPLUG,RM,ROTA",
            "NAME,KNAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,TRAN,MOUNTPOINT",
            "NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT",
        )
        notes: List[str] = []
        for columns in column_sets:
            result = self._run(f"/usr/bin/lsblk -J -o {columns} 2>&1")
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip().split("\n")[0]
                notes.append(f"lsblk({columns[:20]}…): {err}")
                continue
            if not result.stdout.strip():
                notes.append("lsblk: empty output")
                continue
            try:
                payload = json.loads(result.stdout)
                notes.append(f"lsblk ok: {columns.split(',')[0]}…")
                return payload, "; ".join(notes)
            except json.JSONDecodeError as exc:
                notes.append(f"lsblk json error: {exc}")
        return None, "; ".join(notes)

    def _entry_from_block(
        self, block: Dict[str, Any], seen_paths: set[str]
    ) -> Optional[Dict[str, str]]:
        name = block.get("name") or ""
        entry_type = block.get("type") or ""
        path = self._block_path(name, block)

        if not name or entry_type not in ("disk", "part"):
            return None
        if self._should_skip_block(name, entry_type):
            return None
        if not DEVICE_PATH_PATTERN.match(path):
            return None
        if path in seen_paths:
            return None

        seen_paths.add(path)
        mountpoint = block.get("mountpoint") or ""
        is_system = self._is_system_device(path, mountpoint)
        tran = (block.get("tran") or "").lower() or "unknown"
        hotplug = block.get("hotplug")
        removable = block.get("rm")
        transport_label = tran
        if removable in ("1", 1, True) or hotplug in ("1", 1, True):
            transport_label = f"{tran} (hotplug)"

        return {
            "id": path,
            "path": path,
            "name": name,
            "size": block.get("size") or "?",
            "type": entry_type,
            "fstype": block.get("fstype") or "",
            "label": block.get("label") or "",
            "mountpoint": mountpoint,
            "model": (block.get("model") or "").strip(),
            "transport": transport_label,
            "is_system": str(is_system).lower(),
            "can_format": str(entry_type in ("disk", "part") and not is_system).lower(),
        }

    def _merge_findmnt_devices(
        self, entries: List[Dict[str, str]], seen_paths: set[str], debug: List[str]
    ) -> None:
        """Add devices visible to Steam (e.g. /run/media/deck/NVMe1TB)."""
        result = self._run("findmnt -rn -o SOURCE,TARGET,FSTYPE 2>/dev/null || true")
        added = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            source, target = parts[0], parts[1]
            fstype = parts[2] if len(parts) > 2 else ""
            if not source.startswith("/dev/"):
                continue
            if not DEVICE_PATH_PATTERN.match(source):
                continue
            if source in seen_paths:
                continue

            label = self._run(
                f"blkid -s LABEL -o value {shlex.quote(source)} 2>/dev/null || true"
            ).stdout.strip()

            seen_paths.add(source)
            is_system = self._is_system_device(source, target)
            entries.append(
                {
                    "id": source,
                    "path": source,
                    "name": os.path.basename(source),
                    "size": "?",
                    "type": "part",
                    "fstype": fstype,
                    "label": label,
                    "mountpoint": target,
                    "model": "",
                    "transport": "mounted",
                    "is_system": str(is_system).lower(),
                    "can_format": str(not is_system).lower(),
                }
            )
            added += 1
        if added:
            debug.append(f"findmnt: +{added} mounted")

    def _merge_blkid_devices(
        self, entries: List[Dict[str, str]], seen_paths: set[str], debug: List[str]
    ) -> None:
        result = self._run("blkid -o device 2>/dev/null || true")
        added = 0
        for device in result.stdout.splitlines():
            device = device.strip()
            if not device or device in seen_paths:
                continue
            if not DEVICE_PATH_PATTERN.match(device):
                continue
            name = os.path.basename(device)
            if self._should_skip_block(name, "part"):
                continue

            label = self._run(
                f"blkid -s LABEL -o value {shlex.quote(device)} 2>/dev/null || true"
            ).stdout.strip()
            fstype = self._run(
                f"blkid -s TYPE -o value {shlex.quote(device)} 2>/dev/null || true"
            ).stdout.strip()
            mountpoint = self._run(
                f"findmnt -no TARGET {shlex.quote(device)} 2>/dev/null || true"
            ).stdout.strip()
            seen_paths.add(device)
            is_system = self._is_system_device(device, mountpoint)
            entries.append(
                {
                    "id": device,
                    "path": device,
                    "name": name,
                    "size": "?",
                    "type": "part",
                    "fstype": fstype,
                    "label": label,
                    "mountpoint": mountpoint,
                    "model": "",
                    "transport": "blkid",
                    "is_system": str(is_system).lower(),
                    "can_format": str(not is_system).lower(),
                }
            )
            added += 1
        if added:
            debug.append(f"blkid: +{added}")

    def _flatten_lsblk(self, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for device in devices:
            flat.append(device)
            for child in device.get("children") or []:
                flat.extend(self._flatten_lsblk([child]))
        return flat

    async def list_storage_devices(self) -> Dict[str, Any]:
        debug_notes: List[str] = []
        entries: List[Dict[str, str]] = []
        seen_paths: set[str] = set()

        try:
            payload, lsblk_note = self._lsblk_payload()
            debug_notes.append(lsblk_note)
            if payload:
                for block in self._flatten_lsblk(payload.get("blockdevices", [])):
                    entry = self._entry_from_block(block, seen_paths)
                    if entry:
                        entries.append(entry)

            self._merge_findmnt_devices(entries, seen_paths, debug_notes)
            self._merge_blkid_devices(entries, seen_paths, debug_notes)

            entries.sort(
                key=lambda e: (
                    e.get("is_system") == "true",
                    e.get("transport", ""),
                    e.get("path", ""),
                )
            )

            error = ""
            if not entries:
                error = (
                    "no block devices found. "
                    "Try Desktop Mode or check plugin logs."
                )

            decky.logger.info(
                "list_storage_devices: %s devices (%s)",
                len(entries),
                "; ".join(debug_notes),
            )

            return {
                "devices": entries,
                "debug": "; ".join(debug_notes),
                "error": error,
            }
        except Exception as exc:
            decky.logger.exception("list_storage_devices failed")
            return {
                "devices": [],
                "debug": "; ".join(debug_notes),
                "error": str(exc),
            }

    async def list_nvme_devices(self) -> Dict[str, Any]:
        """Backward-compatible alias."""
        return await self.list_storage_devices()

    async def get_config(self) -> Dict[str, Any]:
        return self._load_config()

    async def save_config(
        self, device_path: str, label: str, format_on_apply: bool
    ) -> Dict[str, Any]:
        config = {
            "device_path": self._validate_device_path(device_path)
            if device_path
            else "",
            "label": self._validate_label(label),
            "format_on_apply": bool(format_on_apply),
        }
        self._save_config(config)
        return config

    def _partition_after_format(self, disk_path: str, label: str) -> str:
        partition = self._run(f"blkid -L {shlex.quote(label)}").stdout.strip()
        if partition:
            return partition

        result = self._run(
            f"lsblk -J -o NAME,PATH,TYPE {shlex.quote(disk_path)}", check=True
        )
        payload = json.loads(result.stdout)
        disks = payload.get("blockdevices", [])
        if not disks:
            raise RuntimeError("disk not found after format")

        for child in disks[0].get("children") or []:
            if child.get("type") == "part" and child.get("path"):
                return child["path"]

        raise RuntimeError("partition not found after format")

    def _resolve_target_partition(self, device_path: str, label: str) -> str:
        by_label = self._run(f"blkid -L {shlex.quote(label)}").stdout.strip()
        if by_label:
            return by_label

        device_path = self._validate_device_path(device_path)
        if self._is_partition_path(device_path):
            return device_path

        return self._partition_after_format(device_path, label)

    async def format_storage(self, device_path: str, label: str) -> Dict[str, object]:
        logs: List[str] = []
        errors: List[str] = []

        try:
            label = self._validate_label(label)
            device_path = self._validate_device_path(device_path)

            readonly_status = self._run("steamos-readonly status").stdout
            if "enabled" in readonly_status:
                self._run("steamos-readonly disable", check=True)
                logs.append("disabled steamos readonly mode")

            disk_path = self._disk_from_path(device_path)
            if self._is_system_device(device_path, ""):
                raise RuntimeError("refusing to format a system device")

            result = self._run(
                f"lsblk -ln -o PATH,MOUNTPOINT {shlex.quote(disk_path)}"
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1]:
                    self._run(f"umount -lf {shlex.quote(parts[0])} || true")
                    logs.append(f"unmounted {parts[0]}")

            is_partition = self._is_partition_path(device_path)

            if is_partition:
                target = device_path
                logs.append(f"formatting partition {target}")
                self._run(
                    f"mkfs.ext4 -F -L {shlex.quote(label)} {shlex.quote(target)}",
                    check=True,
                )
            else:
                logs.append(f"partitioning disk {disk_path}")
                self._run(
                    f"parted -s {shlex.quote(disk_path)} mklabel gpt mkpart primary ext4 1MiB 100%",
                    check=True,
                )
                self._run("partprobe || true")
                target = self._partition_after_format(disk_path, label)
                self._run(
                    f"mkfs.ext4 -F -L {shlex.quote(label)} {shlex.quote(target)}",
                    check=True,
                )
                logs.append(f"formatted {target}")

            partition = self._run(f"blkid -L {shlex.quote(label)}").stdout.strip()
            return {
                "ok": True,
                "label": label,
                "partition": partition,
                "logs": logs,
                "errors": errors,
            }
        except Exception as error:
            errors.append(str(error))
            decky.logger.exception("format_storage failed")
            return {"ok": False, "label": label, "logs": logs, "errors": errors}

    async def format_nvme(self, device_path: str, label: str) -> Dict[str, object]:
        """Backward-compatible alias."""
        return await self.format_storage(device_path, label)

    def _disable_legacy_service(self, logs: List[str]) -> None:
        if os.path.isfile(LEGACY_SERVICE_PATH):
            self._run("systemctl disable mount-nvme1tb.service || true")
            self._run("systemctl stop mount-nvme1tb.service || true")
            logs.append("disabled legacy mount-nvme1tb.service")

    def _ensure_steam_layout(self, mount_at: str, label: str, logs: List[str]) -> None:
        steamapps = os.path.join(mount_at, "steamapps")
        if not os.path.isdir(steamapps):
            for relative in (
                "steamapps/common",
                "steamapps/downloading",
                "steamapps/temp",
                "steamapps/shadercache",
            ):
                os.makedirs(os.path.join(mount_at, relative), exist_ok=True)
            self._run(f"chown -R 1000:1000 {shlex.quote(steamapps)}")
            logs.append("created steamapps folder structure")

        vdf_path = os.path.join(mount_at, "libraryfolder.vdf")
        if not os.path.isfile(vdf_path):
            content_id = self._run(
                "shuf -i 1000000000000000000-9999999999999999999 -n 1", check=True
            ).stdout.strip()
            vdf_content = (
                '"libraryfolder"\n'
                "{\n"
                f'\t"contentid"\t\t"{content_id}"\n'
                f'\t"label"\t\t"{label}"\n'
                "}\n"
            )
            self._write_file(vdf_path, vdf_content)
            self._run(f"chown 1000:1000 {shlex.quote(vdf_path)}")
            logs.append("created libraryfolder.vdf")

    async def get_status(
        self, device_path: str = "", label: str = "SteamLibrary"
    ) -> Dict[str, str]:
        label = self._validate_label(label)
        partition = self._run(f"blkid -L {shlex.quote(label)}").stdout.strip()

        if not partition and device_path:
            try:
                partition = self._resolve_target_partition(device_path, label)
            except Exception:
                partition = ""

        mount_target = ""
        if partition:
            mount_target = self._run(
                f"findmnt -no TARGET {shlex.quote(partition)}"
            ).stdout.strip()

        readonly = self._run("steamos-readonly status").stdout.strip()
        service_enabled = self._run(
            "systemctl is-enabled map-storage-automount.service"
        ).stdout.strip()
        service_active = self._run(
            "systemctl is-active map-storage-automount.service"
        ).stdout.strip()

        return {
            "device_path": device_path,
            "label": label,
            "partition": partition,
            "mount_target": mount_target,
            "readonly_status": readonly or "unknown",
            "service_enabled": service_enabled or "unknown",
            "service_active": service_active or "unknown",
            "has_udev_rule": str(os.path.isfile(UDEV_RULE_PATH)).lower(),
            "has_mount_script": str(os.path.isfile(MOUNT_SCRIPT_PATH)).lower(),
            "has_service_file": str(os.path.isfile(SERVICE_PATH)).lower(),
            "configured_label": self._load_config().get("label", label),
        }

    async def get_service_logs(self, lines: int = 80) -> str:
        safe_lines = max(20, min(lines, 300))
        result = self._run(
            f"journalctl -u map-storage-automount.service -n {safe_lines} --no-pager"
        )
        legacy = self._run(
            f"journalctl -u mount-nvme1tb.service -n {safe_lines} --no-pager"
        )
        chunks = [
            (result.stdout or result.stderr or "").strip(),
            (legacy.stdout or legacy.stderr or "").strip(),
        ]
        return "\n\n".join(chunk for chunk in chunks if chunk)

    async def apply_storage_fix(
        self, device_path: str, label: str, format_drive: bool
    ) -> Dict[str, object]:
        logs: List[str] = []
        errors: List[str] = []
        deck_user = getattr(decky, "DECKY_USER", "deck")

        try:
            label = self._validate_label(label)
            if not device_path:
                raise RuntimeError("select a storage device first")

            device_path = self._validate_device_path(device_path)
            self._save_config(
                {
                    "device_path": device_path,
                    "label": label,
                    "format_on_apply": bool(format_drive),
                }
            )

            if format_drive:
                fmt = await self.format_storage(device_path, label)
                logs.extend(fmt.get("logs", []))
                if not fmt.get("ok"):
                    errors.extend(fmt.get("errors", []))
                    raise RuntimeError(
                        errors[-1] if errors else "format failed"
                    )

            readonly_status = self._run("steamos-readonly status").stdout
            if "enabled" in readonly_status:
                self._run("steamos-readonly disable", check=True)
                logs.append("disabled steamos readonly mode")

            partition = self._resolve_target_partition(device_path, label)
            if not partition:
                raise RuntimeError(
                    f"no partition found for label '{label}'. "
                    "Enable format or pick a partitioned drive."
                )
            logs.append(f"target partition: {partition}")

            self._disable_legacy_service(logs)

            self._write_file(UDEV_RULE_PATH, UDEV_RULE_TEMPLATE.format(label=label))
            logs.append(f"wrote udev rule: {UDEV_RULE_PATH}")

            mount_script = MOUNT_SCRIPT_TEMPLATE.format(
                label=label, deck_user=deck_user
            )
            self._write_file(MOUNT_SCRIPT_PATH, mount_script, 0o755)
            logs.append(f"wrote mount helper: {MOUNT_SCRIPT_PATH}")

            service_content = SERVICE_TEMPLATE.format(
                label=label, mount_script=MOUNT_SCRIPT_PATH
            )
            self._write_file(SERVICE_PATH, service_content)
            logs.append(f"wrote systemd service: {SERVICE_PATH}")

            self._run("udevadm control --reload-rules || true")
            self._run("udevadm trigger || true")
            self._run("systemctl daemon-reload", check=True)
            self._run("systemctl enable map-storage-automount.service", check=True)
            self._run("systemctl restart map-storage-automount.service", check=True)
            logs.append("enabled and restarted map-storage-automount.service")

            mount_target = self._run(
                f"findmnt -no TARGET {shlex.quote(partition)}"
            ).stdout.strip()
            if mount_target:
                self._ensure_steam_layout(mount_target, label, logs)
                logs.append(f"mounted at: {mount_target}")
            else:
                logs.append("not mounted now; service will retry on boot")

            return {
                "ok": True,
                "label": label,
                "device_path": device_path,
                "partition": partition,
                "mount_target": mount_target,
                "formatted": format_drive,
                "logs": logs,
                "errors": errors,
            }
        except Exception as error:
            errors.append(str(error))
            decky.logger.exception("apply_storage_fix failed")
            return {
                "ok": False,
                "label": label,
                "device_path": device_path,
                "formatted": format_drive,
                "logs": logs,
                "errors": errors,
            }

    async def apply_nvme_fix(
        self, device_path: str, label: str, format_drive: bool
    ) -> Dict[str, object]:
        """Backward-compatible alias."""
        return await self.apply_storage_fix(device_path, label, format_drive)

    async def _main(self):
        decky.logger.info("map-storage backend loaded")

    async def _unload(self):
        decky.logger.info("map-storage backend unloaded")

    async def _uninstall(self):
        decky.logger.info("map-storage backend uninstalled")

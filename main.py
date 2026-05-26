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
    PARTITION=$(/usr/bin/blkid -L "$LABEL" 2>/dev/null || echo "")

    if [[ -z "$PARTITION" ]]; then
        echo "map-storage-mount[$i/$MAX_RETRIES]: partition not found, waiting..."
        sleep $RETRY_DELAY
        continue
    fi

    if /usr/bin/findmnt -no TARGET "$PARTITION" >/dev/null 2>&1; then
        MOUNT_AT=$(/usr/bin/findmnt -no TARGET "$PARTITION")
        chown 1000:1000 "$MOUNT_AT" 2>/dev/null || true
        echo "map-storage-mount: already mounted at $MOUNT_AT"
        exit 0
    fi

    if ! pidof udisksd >/dev/null 2>&1 && ! pgrep udisksd >/dev/null 2>&1; then
        echo "map-storage-mount[$i/$MAX_RETRIES]: udisksd not ready, waiting..."
        sleep $RETRY_DELAY
        continue
    fi

    if runuser -u "$DECK_USER" -- /usr/bin/udisksctl mount -b "$PARTITION" --no-user-interaction >/dev/null 2>&1; then
        sleep 1
        MOUNT_AT=$(/usr/bin/findmnt -no TARGET "$PARTITION" 2>/dev/null || echo "")
        if [[ -n "$MOUNT_AT" ]]; then
            chown 1000:1000 "$MOUNT_AT" 2>/dev/null || true
            echo "map-storage-mount: mounted at $MOUNT_AT"
        fi
        exit 0
    fi

    sleep $RETRY_DELAY
done

PARTITION=$(/usr/bin/blkid -L "$LABEL" 2>/dev/null || echo "")
if [[ -n "$PARTITION" ]]; then
    MOUNT_POINT="/run/media/$DECK_USER/$LABEL"
    mkdir -p "$MOUNT_POINT"
    /usr/bin/mount -o rw,noatime "$PARTITION" "$MOUNT_POINT"
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
    _PATH_ENV = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    _CMD_TIMEOUT_SEC = 45

    def _tool(self, name: str) -> str:
        for candidate in (f"/usr/bin/{name}", f"/bin/{name}"):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return name

    def _clean_env(self) -> Dict[str, str]:
        """Avoid Decky-inherited LD_* breaking /bin/sh (symbol lookup errors)."""
        env = {
            "PATH": self._PATH_ENV,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if os.getuid() == 0:
            env["HOME"] = "/root"
        else:
            env["HOME"] = os.environ.get(
                "HOME", getattr(decky, "DECKY_USER_HOME", "/home/deck")
            )
        return env

    def _run_cli(
        self, args: List[str], check: bool = False
    ) -> subprocess.CompletedProcess:
        decky.logger.info("exec argv: %s", args)
        try:
            result = subprocess.run(
                args,
                text=True,
                capture_output=True,
                env=self._clean_env(),
                timeout=self._CMD_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"command timed out after {self._CMD_TIMEOUT_SEC}s") from exc
        if check and result.returncode != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or " ".join(args)).strip()
            )
        return result

    def _run(self, command: str, check: bool = False) -> subprocess.CompletedProcess:
        decky.logger.info("exec: %s", command)
        return self._run_cli(["/bin/bash", "-c", command], check=check)

    def _run_as_deck_user(self, command: str, deck_user: str) -> subprocess.CompletedProcess:
        if os.getuid() == 0:
            return self._run_cli(
                ["/usr/bin/runuser", "-u", deck_user, "--", "/bin/bash", "-c", command]
            )
        return self._run(f"/usr/bin/sudo -u {shlex.quote(deck_user)} {command}")

    def _blkid_field(self, device: str, field: str) -> str:
        blkid = self._tool("blkid")
        result = self._run_cli(
            [blkid, f"-s", field.upper(), "-o", "value", device],
        )
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def _findmnt_target(self, device: str) -> str:
        findmnt = self._tool("findmnt")
        result = self._run_cli([findmnt, "-no", "TARGET", device])
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def _lsblk_size(self, device: str) -> str:
        lsblk = self._tool("lsblk")
        result = self._run_cli([lsblk, "-no", "SIZE", device])
        if result.returncode != 0:
            return "?"
        return (result.stdout or "").strip() or "?"

    def _label_on_device(self, device_path: str) -> str:
        return self._blkid_field(device_path, "LABEL")

    def _storage_display_label(self, label: str, mountpoint: str) -> str:
        """Name shown in Steam Settings (ext4 LABEL or /run/media/deck/<name>)."""
        if label:
            return label
        mountpoint = (mountpoint or "").rstrip("/")
        deck_prefix = f"/run/media/{getattr(decky, 'DECKY_USER', 'deck')}/"
        if mountpoint.startswith(deck_prefix):
            return os.path.basename(mountpoint)
        if mountpoint.startswith("/run/media/"):
            return os.path.basename(mountpoint)
        return ""

    def _enrich_device(self, path: str) -> Optional[Dict[str, str]]:
        if not DEVICE_PATH_PATTERN.match(path):
            return None
        name = os.path.basename(path)
        entry_type = "part" if self._is_partition_path(path) else "disk"
        if self._should_skip_block(name, entry_type):
            return None

        label = self._label_on_device(path)
        fstype = self._blkid_field(path, "TYPE")
        mountpoint = self._findmnt_target(path)
        size = self._lsblk_size(path)
        is_system = self._is_system_device(path, mountpoint)

        transport = "unmounted"
        if mountpoint.lower().startswith("/run/media/"):
            transport = "steam-library"
        elif mountpoint:
            transport = "mounted"

        if fstype.lower() in ("crypto_luks",):
            transport = "encrypted"

        storage_label = self._storage_display_label(label, mountpoint)

        return {
            "id": path,
            "path": path,
            "name": name,
            "size": size,
            "type": entry_type,
            "fstype": fstype or ("crypto_LUKS" if "encrypted" in transport else ""),
            "label": label,
            "storage_label": storage_label,
            "mountpoint": mountpoint,
            "model": "",
            "transport": transport,
            "is_system": str(is_system).lower(),
            "can_format": str(entry_type in ("disk", "part") and not is_system).lower(),
            "is_mounted": str(bool(mountpoint)).lower(),
        }

    def _mark_internal_nvme(self, entries: List[Dict[str, str]]) -> None:
        """Steam Deck internal storage is usually nvme0n1; expansion is nvme1n1."""
        for entry in entries:
            path = entry.get("path", "")
            if re.match(r"^/dev/nvme0n\d", path) and entry.get("transport") != "steam-library":
                entry["is_system"] = "true"
                entry["can_format"] = "false"
                if not entry.get("transport"):
                    entry["transport"] = "internal"

    def _resolve_working_label(self, device_path: str, label: str) -> str:
        device_path = self._validate_device_path(device_path)
        on_device = self._label_on_device(device_path)
        if on_device:
            return self._validate_label(on_device)
        return self._validate_label(label)

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
        findmnt = self._tool("findmnt")
        result = self._run(f"{findmnt} -no SOURCE / /home 2>/dev/null || true")
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _is_system_device(self, path: str, mountpoint: str) -> bool:
        critical = ("/", "/home", "/var", "/usr", "/boot", "/etc")

        if not mountpoint:
            findmnt = self._tool("findmnt")
            mountpoint = self._run(
                f"{findmnt} -no TARGET {shlex.quote(path)} 2>/dev/null || true"
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
        lsblk = self._tool("lsblk")
        for columns in column_sets:
            result = self._run(f"{lsblk} -J -o {columns} 2>&1")
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

    def _append_device(
        self,
        entries: List[Dict[str, str]],
        seen_paths: set[str],
        path: str,
        mountpoint: str,
        fstype: str,
        label: str,
        transport: str,
        entry_type: str = "part",
        size: str = "?",
    ) -> bool:
        if not path or path in seen_paths:
            return False
        if not DEVICE_PATH_PATTERN.match(path):
            return False
        name = os.path.basename(path)
        if self._should_skip_block(name, entry_type):
            return False

        seen_paths.add(path)
        is_system = self._is_system_device(path, mountpoint)
        entries.append(
            {
                "id": path,
                "path": path,
                "name": name,
                "size": size,
                "type": entry_type,
                "fstype": fstype or "",
                "label": label or "",
                "mountpoint": mountpoint or "",
                "model": "",
                "transport": transport,
                "is_system": str(is_system).lower(),
                "can_format": str(not is_system).lower(),
            }
        )
        return True

    def _discover_paths(self) -> Tuple[set[str], List[str]]:
        """Collect block device paths, then enrich each via blkid/findmnt/lsblk."""
        paths: set[str] = set()
        notes: List[str] = []

        deck_user = getattr(decky, "DECKY_USER", "deck")
        media_root = f"/run/media/{deck_user}"
        media_count = 0
        if os.path.isdir(media_root):
            findmnt = self._tool("findmnt")
            for folder_name in sorted(os.listdir(media_root)):
                mountpoint = os.path.join(media_root, folder_name)
                if not os.path.isdir(mountpoint):
                    continue
                result = self._run_cli([findmnt, "-no", "SOURCE", mountpoint])
                source = (result.stdout or "").strip()
                if DEVICE_PATH_PATTERN.match(source):
                    paths.add(source)
                    media_count += 1
        if media_count:
            notes.append(f"run/media: {media_count}")

        findmnt = self._tool("findmnt")
        result = self._run(f"{findmnt} -rn -o SOURCE,TARGET 2>/dev/null || true")
        findmnt_count = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            source = parts[0]
            if DEVICE_PATH_PATTERN.match(source):
                paths.add(source)
                findmnt_count += 1
        if findmnt_count:
            notes.append(f"findmnt: {findmnt_count}")

        payload, lsblk_note = self._lsblk_payload()
        notes.append(lsblk_note)
        if payload:
            for block in self._flatten_lsblk(payload.get("blockdevices", [])):
                name = block.get("name") or ""
                entry_type = block.get("type") or ""
                path = self._block_path(name, block)
                if entry_type in ("disk", "part") and DEVICE_PATH_PATTERN.match(path):
                    if not self._should_skip_block(name, entry_type):
                        paths.add(path)

        blkid = self._tool("blkid")
        result = self._run(f"{blkid} -o device 2>/dev/null || true")
        blkid_count = 0
        for device in result.stdout.splitlines():
            device = device.strip()
            if not DEVICE_PATH_PATTERN.match(device):
                continue
            name = os.path.basename(device)
            if self._should_skip_block(name, "part"):
                continue
            paths.add(device)
            blkid_count += 1
        if blkid_count:
            notes.append(f"blkid: {blkid_count}")

        proc_path = "/proc/partitions"
        proc_count = 0
        if os.path.isfile(proc_path):
            with open(proc_path, encoding="utf-8") as file:
                for line in file.readlines()[2:]:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    name = parts[-1]
                    if self._should_skip_block(name, "part"):
                        continue
                    path = f"/dev/{name}"
                    if DEVICE_PATH_PATTERN.match(path):
                        paths.add(path)
                        proc_count += 1
        if proc_count:
            notes.append(f"proc: {proc_count}")

        return paths, notes

    def _build_scan_result(self) -> Dict[str, Any]:
        debug_notes: List[str] = []
        debug_notes.append(f"plugin {getattr(decky, 'DECKY_PLUGIN_VERSION', '?')}")
        debug_notes.append(f"user {getattr(decky, 'DECKY_USER', '?')}")

        paths, discover_notes = self._discover_paths()
        debug_notes.extend(discover_notes)

        entries: List[Dict[str, str]] = []
        for path in sorted(paths):
            entry = self._enrich_device(path)
            if entry:
                entries.append(entry)

        self._mark_internal_nvme(entries)

        entries.sort(
            key=lambda e: (
                e.get("is_system") == "true",
                e.get("is_mounted") != "true",
                e.get("transport") != "steam-library",
                e.get("path", ""),
            )
        )

        error = ""
        if not entries:
            error = (
                "no storage devices found. "
                "Check plugin logs under homebrew/logs."
            )

        return {
            "devices": entries,
            "debug": "; ".join(debug_notes),
            "error": error,
            "ok": not bool(error),
            "count": len(entries),
        }

    async def ping(self) -> Dict[str, str]:
        return {
            "status": "ok",
            "version": getattr(decky, "DECKY_PLUGIN_VERSION", "unknown"),
            "user": getattr(decky, "DECKY_USER", "deck"),
        }

    def _flatten_lsblk(self, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for device in devices:
            flat.append(device)
            for child in device.get("children") or []:
                flat.extend(self._flatten_lsblk([child]))
        return flat

    async def list_storage_devices(self) -> str:
        """
        Returns JSON string for reliable Decky JS bridge parsing.
        Shape: { devices, debug, error, ok, count }
        """
        try:
            payload = self._build_scan_result()
            decky.logger.info(
                "list_storage_devices: %s devices",
                payload.get("count", 0),
            )
            return json.dumps(payload)
        except Exception as exc:
            decky.logger.exception("list_storage_devices failed")
            return json.dumps(
                {
                    "devices": [],
                    "debug": "",
                    "error": str(exc),
                    "ok": False,
                    "count": 0,
                }
            )

    async def list_nvme_devices(self) -> str:
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
        blkid = self._tool("blkid")
        partition = self._run_cli([blkid, "-L", label]).stdout.strip()
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
        label = self._validate_label(label)
        device_path = self._validate_device_path(device_path)

        blkid = self._tool("blkid")
        by_label = self._run_cli([blkid, "-L", label]).stdout.strip()
        if by_label:
            return by_label

        if self._is_partition_path(device_path):
            return device_path

        return self._partition_after_format(device_path, label)

    def _try_mount_as_deck(
        self, partition: str, deck_user: str, logs: List[str]
    ) -> str:
        udisksctl = self._tool("udisksctl")
        if os.getuid() == 0:
            result = self._run_cli(
                [
                    "/usr/bin/runuser",
                    "-u",
                    deck_user,
                    "--",
                    udisksctl,
                    "mount",
                    "-b",
                    partition,
                    "--no-user-interaction",
                ]
            )
        else:
            result = self._run(
                f"/usr/bin/sudo -u {shlex.quote(deck_user)} "
                f"{udisksctl} mount -b {shlex.quote(partition)} --no-user-interaction"
            )
        if result.returncode == 0:
            logs.append("mounted via udisksctl")
            return self._findmnt_target(partition)
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            logs.append(f"udisksctl mount: {detail}")
        return ""

    async def format_storage(self, device_path: str, label: str) -> Dict[str, object]:
        logs: List[str] = []
        errors: List[str] = []

        try:
            label = self._validate_label(label)
            device_path = self._validate_device_path(device_path)

            readonly = self._run_cli([self._tool("steamos-readonly"), "status"])
            if "enabled" in (readonly.stdout or ""):
                self._run_cli(
                    [self._tool("steamos-readonly"), "disable"], check=True
                )
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

            partition = self._run_cli(
                [self._tool("blkid"), "-L", label]
            ).stdout.strip()
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
        systemctl = self._tool("systemctl")
        if os.path.isfile(LEGACY_SERVICE_PATH):
            self._run_cli([systemctl, "disable", "mount-nvme1tb.service"])
            self._run_cli([systemctl, "stop", "mount-nvme1tb.service"])
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
        working_label = label
        if device_path:
            try:
                working_label = self._resolve_working_label(device_path, label)
            except Exception:
                working_label = self._validate_label(label)
        else:
            working_label = self._validate_label(label)

        partition = ""
        if device_path:
            try:
                device_path = self._validate_device_path(device_path)
                if self._is_partition_path(device_path):
                    partition = device_path
            except Exception:
                device_path = ""

        if not partition:
            partition = self._run_cli(
                [self._tool("blkid"), "-L", working_label]
            ).stdout.strip()
        if not partition and device_path:
            try:
                partition = self._resolve_target_partition(device_path, working_label)
            except Exception:
                partition = ""

        mount_target = self._findmnt_target(partition) if partition else ""
        on_disk_label = self._label_on_device(partition) if partition else ""
        storage_label = self._storage_display_label(on_disk_label, mount_target)

        readonly = self._run_cli(
            [self._tool("steamos-readonly"), "status"]
        ).stdout.strip()
        systemctl = self._tool("systemctl")
        service_enabled = self._run_cli(
            [systemctl, "is-enabled", "map-storage-automount.service"]
        ).stdout.strip()
        service_active = self._run_cli(
            [systemctl, "is-active", "map-storage-automount.service"]
        ).stdout.strip()

        return {
            "device_path": device_path,
            "label": working_label,
            "storage_label": storage_label or working_label,
            "partition": partition,
            "mount_target": mount_target,
            "readonly_status": readonly or "unknown",
            "service_enabled": service_enabled or "unknown",
            "service_active": service_active or "unknown",
            "has_udev_rule": str(os.path.isfile(UDEV_RULE_PATH)).lower(),
            "has_mount_script": str(os.path.isfile(MOUNT_SCRIPT_PATH)).lower(),
            "has_service_file": str(os.path.isfile(SERVICE_PATH)).lower(),
            "configured_label": self._load_config().get("label", working_label),
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
            if not device_path:
                raise RuntimeError("select a storage device first")

            device_path = self._validate_device_path(device_path)

            if not format_drive and not self._is_partition_path(device_path):
                raise RuntimeError(
                    "select a partition (e.g. /dev/nvme1n1p1), not the whole disk. "
                    "Enable format to partition the disk, or pick the partition that "
                    "has your Steam library (often labeled NVMe1TB)."
                )

            if not format_drive:
                label = self._resolve_working_label(device_path, label)
            else:
                label = self._validate_label(label)

            on_device = self._label_on_device(device_path)
            if (
                not format_drive
                and self._is_partition_path(device_path)
                and not on_device
            ):
                raise RuntimeError(
                    "selected partition has no filesystem. "
                    "Enable format or pick a formatted partition."
                )

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

            readonly = self._run_cli([self._tool("steamos-readonly"), "status"])
            if "enabled" in (readonly.stdout or ""):
                self._run_cli(
                    [self._tool("steamos-readonly"), "disable"], check=True
                )
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

            udevadm = self._tool("udevadm")
            self._run_cli([udevadm, "control", "--reload-rules"])
            self._run_cli([udevadm, "trigger"])
            systemctl = self._tool("systemctl")
            self._run_cli([systemctl, "daemon-reload"], check=True)
            self._run_cli(
                [systemctl, "enable", "map-storage-automount.service"], check=True
            )
            self._run_cli(
                [systemctl, "restart", "map-storage-automount.service"], check=True
            )
            logs.append("enabled and restarted map-storage-automount.service")

            mount_target = self._findmnt_target(partition)
            if not mount_target:
                mount_target = self._try_mount_as_deck(partition, deck_user, logs)
            if not mount_target:
                self._run_cli([systemctl, "start", "map-storage-automount.service"])
                mount_target = self._findmnt_target(partition)
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

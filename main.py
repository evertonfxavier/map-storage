import asyncio
import json
import os
import pwd
import random
import re
import subprocess
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

import decky

ETC_DIR = "/etc/map-storage"
HELPER_PATH = os.path.join(ETC_DIR, "map-storage-mount.sh")
UDEV_RULE_PATH = "/etc/udev/rules.d/99-map-storage-automount.rules"
SERVICE_NAME = "map-storage-automount.service"
SERVICE_PATH = f"/etc/systemd/system/{SERVICE_NAME}"
LEGACY_HELPER_PATH = "/usr/local/bin/map-storage-mount.sh"
LEGACY_SERVICE_NAME = "mount-nvme1tb.service"
LEGACY_SERVICE_PATH = f"/etc/systemd/system/{LEGACY_SERVICE_NAME}"
PARTSETS_PATH = "/efi/SteamOS/partsets/all"
CONFIG_PATH = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "config.json")
CONFIG_VERSION = 2

LABEL_MAX_LEN = 16
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
UUID_PATTERN = re.compile(r"^[A-Za-z0-9-]{4,64}$")

DEVICE_PATH_PATTERN = re.compile(
    r"^/dev/(?:"
    r"nvme\d+n\d+(?:p\d+)?|"
    r"sd[a-z]+\d*|mmcblk\d+(?:p\d+)?|"
    r"vd[a-z]+\d*|hd[a-z]+\d*"
    r")$"
)
SKIP_NAME_PREFIXES = ("loop", "ram", "zram", "sr", "fd", "dm-", "md", "nbd", "rbd")
SUPPORTED_FSTYPES = frozenset({"ext4", "btrfs", "xfs", "f2fs"})
CRITICAL_MOUNTS = frozenset({"/", "/home", "/var", "/usr", "/boot", "/efi", "/esp", "/etc"})

LSBLK_COLUMN_SETS = (
    "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTUUID,MODEL,SERIAL,TRAN,MOUNTPOINTS,HOTPLUG,RM",
    "NAME,KNAME,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTUUID,MODEL,SERIAL,TRAN,MOUNTPOINT,HOTPLUG,RM",
    "NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT",
)

CMD_TIMEOUT_SEC = 45
CLEAN_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

UDEV_RULES_HEADER = """# Managed by Map Storage - regenerated on every plugin load, do not edit.
# Drives are matched by filesystem UUID: /dev/nvmeXnY names swap between boots.
SUBSYSTEM!="block", GOTO="map_storage_end"
ENV{ID_FS_USAGE}!="filesystem", GOTO="map_storage_end"
"""

UDEV_RULE_TEMPLATE = (
    'ACTION=="add", ENV{{ID_FS_UUID}}=="{uuid}", '
    'RUN+="/usr/bin/systemd-run --no-block --collect {helper} --wait 5 {uuid}"\n'
)

SERVICE_TEMPLATE = """# Managed by Map Storage - regenerated on every plugin load, do not edit.
[Unit]
Description=Map Storage automount (Steam library drives by UUID)
After=udisks2.service systemd-udevd.service local-fs.target
Wants=udisks2.service
Before=sddm.service

[Service]
Type=oneshot
ExecStart={helper} --wait 10 {uuids}
RemainAfterExit=yes
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
"""

# Mounts by UUID as root through udisks2 with `as-user` (same call SteamOS uses
# for SD cards). A plain `udisksctl mount` run as the deck user is refused by
# polkit for non-removable NVMe drives (HintSystem), which is why the library
# used to come up late, after Steam had already started.
HELPER_TEMPLATE = r"""#!/bin/bash
# Managed by Map Storage - regenerated on every plugin load, do not edit.
# Usage: map-storage-mount.sh [--wait SECONDS] UUID...
set -u

DECK_USER="@DECK_USER@"
WAIT=0
if [[ "${1:-}" == "--wait" ]]; then
    WAIT="${2:-0}"
    shift 2 || shift $#
fi
[[ "$WAIT" =~ ^[0-9]+$ ]] || WAIT=0

DECK_UID=$(id -u "$DECK_USER" 2>/dev/null) || { echo "map-storage-mount: unknown user $DECK_USER" >&2; exit 1; }
DECK_GID=$(id -g "$DECK_USER")

exec 9>/run/map-storage-mount.lock
flock -w 50 9 || exit 1

log() { echo "map-storage-mount: $*"; }

find_device() {
    local dev
    dev=$(/usr/bin/blkid -U "$1" 2>/dev/null) && [[ -n "$dev" ]] && { echo "$dev"; return 0; }
    dev=$(readlink -f "/dev/disk/by-uuid/$1" 2>/dev/null)
    [[ -b "$dev" ]] && { echo "$dev"; return 0; }
    return 1
}

mount_target() {
    /usr/bin/findmnt -no TARGET "$1" 2>/dev/null | head -n1
}

udisks_mount() {
    local base="${1##*/}" attempt
    for attempt in 1 2 3; do
        if /usr/bin/busctl call --timeout=8 --allow-interactive-authorization=false \
            --expect-reply=true --json=short \
            org.freedesktop.UDisks2 "/org/freedesktop/UDisks2/block_devices/${base}" \
            org.freedesktop.UDisks2.Filesystem Mount 'a{sv}' 3 \
            as-user s "$DECK_USER" auth.no_user_interaction b true \
            options s "rw,noatime" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

raw_mount() {
    local dev="$1" uuid="$2" label mp
    label=$(/usr/bin/blkid -s LABEL -o value "$dev" 2>/dev/null)
    label="${label//\//_}"
    mp="/run/media/${DECK_USER}/${label:-$uuid}"
    mkdir -p "$mp" && /usr/bin/mount -o rw,noatime "$dev" "$mp" && echo "$mp"
}

ensure_writable() {
    if ! setpriv --clear-groups --reuid "$DECK_UID" --regid "$DECK_GID" test -w "$1"; then
        chown "$DECK_UID:$DECK_GID" "$1" 2>/dev/null || chmod 777 "$1" 2>/dev/null || true
    fi
}

rc=0
deadline=$((SECONDS + WAIT))
for uuid in "$@"; do
    if [[ ! "$uuid" =~ ^[A-Za-z0-9-]{4,64}$ ]]; then
        log "ignoring invalid uuid"
        rc=1
        continue
    fi

    dev=""
    while :; do
        dev=$(find_device "$uuid") && break
        (( SECONDS >= deadline )) && break
        sleep 1
    done
    if [[ -z "$dev" ]]; then
        log "$uuid: not present"
        rc=1
        continue
    fi

    /usr/bin/udevadm settle --timeout=10 >/dev/null 2>&1 || true

    mp=$(mount_target "$dev")
    if [[ -z "$mp" ]] && udisks_mount "$dev"; then
        mp=$(mount_target "$dev")
        [[ -n "$mp" ]] && log "$uuid: mounted $dev at $mp (udisks)"
    fi
    if [[ -z "$mp" ]]; then
        mp=$(raw_mount "$dev" "$uuid") && log "$uuid: mounted $dev at $mp (udisks refused, used mount)"
    fi
    if [[ -z "$mp" ]]; then
        log "$uuid: mount of $dev failed"
        rc=1
        continue
    fi

    ensure_writable "$mp"
    log "$uuid: ready at $mp"
done
exit $rc
"""

_LOCK = threading.RLock()


def tool(name: str) -> str:
    for candidate in (f"/usr/bin/{name}", f"/bin/{name}", f"/usr/sbin/{name}", f"/sbin/{name}"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return name


def clean_env() -> Dict[str, str]:
    """Drop Decky-inherited LD_* variables that break system binaries."""
    home = "/root" if os.getuid() == 0 else getattr(decky, "DECKY_USER_HOME", "/home/deck")
    return {"PATH": CLEAN_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": home}


def run(args: List[str], timeout: int = CMD_TIMEOUT_SEC) -> subprocess.CompletedProcess:
    """Run a command without a shell; never raises, failures are in returncode."""
    decky.logger.info("exec: %s", args)
    try:
        return subprocess.run(
            args, text=True, capture_output=True, env=clean_env(), timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"timed out after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def out(result: subprocess.CompletedProcess) -> str:
    return (result.stdout or "").strip()


def err(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip()


def deck_user() -> str:
    return getattr(decky, "DECKY_USER", "deck")


def deck_ids() -> Tuple[int, int]:
    try:
        entry = pwd.getpwnam(deck_user())
        return entry.pw_uid, entry.pw_gid
    except KeyError:
        return 1000, 1000


def validate_label(label: str) -> str:
    label = (label or "").strip()
    if not label or len(label) > LABEL_MAX_LEN:
        raise RuntimeError(f"label must be 1-{LABEL_MAX_LEN} chars (letters, numbers, _ or -)")
    if not LABEL_PATTERN.match(label):
        raise RuntimeError("invalid label characters")
    return label


def validate_uuid(uuid: str) -> str:
    uuid = (uuid or "").strip()
    if not UUID_PATTERN.match(uuid):
        raise RuntimeError(f"invalid filesystem UUID: {uuid!r}")
    return uuid


def validate_device_path(path: str) -> str:
    path = (path or "").strip()
    if not DEVICE_PATH_PATTERN.match(path):
        raise RuntimeError(f"unsupported or invalid device path: {path}")
    return path


def _truthy(value: Any) -> bool:
    return value in (True, 1, "1", "true")


# ---------------------------------------------------------------- block devices


def read_lsblk() -> Tuple[List[Dict[str, Any]], str]:
    """lsblk JSON with decreasing column sets (util-linux differs per SteamOS build)."""
    notes: List[str] = []
    for columns in LSBLK_COLUMN_SETS:
        result = run([tool("lsblk"), "-J", "-o", columns])
        if result.returncode != 0 or not out(result):
            notes.append(f"lsblk({columns.split(',')[0]}..): {err(result)[:80] or 'empty'}")
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            notes.append(f"lsblk json: {exc}")
            continue
        return payload.get("blockdevices", []), "; ".join(notes)
    return [], "; ".join(notes)


def flatten_blocks(
    nodes: List[Dict[str, Any]], parent: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Flatten the lsblk tree into dicts that remember their parent disk."""
    blocks: List[Dict[str, Any]] = []
    for node in nodes:
        name = node.get("name") or ""
        path = node.get("path") or node.get("kname") or name
        if path and not path.startswith("/dev/"):
            path = f"/dev/{path}"
        kind = node.get("type") or ""

        mountpoints = node.get("mountpoints")
        if mountpoints is None:
            mountpoints = [node.get("mountpoint")]
        mountpoints = [m for m in mountpoints if m and not str(m).startswith("[")]

        if kind == "disk" or parent is None:
            disk = path
            inherited = node
        else:
            disk = parent["path"]
            inherited = parent
        model = (node.get("model") or inherited.get("model") or "").strip()
        serial = (node.get("serial") or inherited.get("serial") or "").strip()
        tran = (node.get("tran") or inherited.get("tran") or "").lower()

        children = node.get("children") or []
        blocks.append(
            {
                "path": path,
                "name": os.path.basename(path),
                "type": kind,
                "size": node.get("size") or "?",
                "fstype": (node.get("fstype") or "").lower(),
                "label": node.get("label") or "",
                "uuid": node.get("uuid") or "",
                "partuuid": (node.get("partuuid") or "").lower(),
                "model": model,
                "serial": serial,
                "tran": tran,
                "removable": _truthy(node.get("hotplug")) or _truthy(node.get("rm")),
                "mountpoints": mountpoints,
                "disk": disk,
                "has_children": bool(children),
            }
        )
        context = {"path": disk, "model": model, "serial": serial, "tran": tran}
        blocks.extend(flatten_blocks(children, context))
    return blocks


def load_partsets() -> Set[str]:
    """PARTUUIDs of SteamOS A/B system partitions (rootfs, var, efi, esp...)."""
    uuids: Set[str] = set()
    try:
        with open(PARTSETS_PATH, encoding="utf-8") as file:
            for line in file:
                parts = line.split()
                if len(parts) >= 2:
                    uuids.add(parts[1].lower())
    except OSError:
        pass
    return uuids


def os_disk_paths(blocks: List[Dict[str, Any]], partsets: Set[str]) -> Set[str]:
    """
    Disks that hold the running OS. Derived from what is mounted at / /home /var
    /efi ... (and SteamOS partsets), never from an nvme index: the internal drive
    can enumerate as nvme0 on one boot and nvme1 on the next.
    """
    disks: Set[str] = set()
    for block in blocks:
        if any(mp in CRITICAL_MOUNTS for mp in block["mountpoints"]) or (
            block["partuuid"] and block["partuuid"] in partsets
        ):
            disks.add(block["disk"])
    return disks


def fingerprint(block: Dict[str, Any]) -> str:
    """Stable identity for confirming a destructive action hits the same media."""
    if block["partuuid"]:
        return f"partuuid:{block['partuuid']}"
    if block["uuid"]:
        return f"uuid:{block['uuid']}"
    if block["type"] == "disk":
        return f"disk:{block['serial'] or block['model']}:{block['size']}"
    return f"path:{block['path']}"


def classify_blocks(
    blocks: List[Dict[str, Any]],
    os_disks: Set[str],
    partsets: Set[str],
    enabled_uuids: Set[str],
) -> List[Dict[str, Any]]:
    os_known = bool(os_disks)
    media_prefix = f"/run/media/{deck_user()}/"
    devices: List[Dict[str, Any]] = []

    for block in blocks:
        if block["type"] not in ("disk", "part"):
            continue
        if not DEVICE_PATH_PATTERN.match(block["path"]):
            continue
        if any(block["name"].startswith(prefix) for prefix in SKIP_NAME_PREFIXES):
            continue

        is_system = block["disk"] in os_disks or (
            bool(block["partuuid"]) and block["partuuid"] in partsets
        )
        container = block["type"] == "disk" and block["has_children"]
        eligible = (
            os_known
            and not is_system
            and not container
            and block["fstype"] in SUPPORTED_FSTYPES
            and bool(UUID_PATTERN.match(block["uuid"]))
        )
        mountpoints = block["mountpoints"]
        mountpoint = next(
            (mp for mp in mountpoints if mp.startswith(media_prefix)),
            mountpoints[0] if mountpoints else "",
        )
        devices.append(
            {
                "path": block["path"],
                "name": block["name"],
                "type": block["type"],
                "size": block["size"],
                "fstype": block["fstype"],
                "label": block["label"],
                "uuid": block["uuid"],
                "model": block["model"],
                "transport": block["tran"],
                "removable": block["removable"],
                "mountpoint": mountpoint,
                "mounted": bool(mountpoints),
                "is_system": is_system,
                "eligible": eligible,
                "can_format": os_known and not is_system,
                "enabled": block["uuid"] in enabled_uuids,
                "fingerprint": fingerprint(block),
                "disk": block["disk"],
                "display_name": block["label"] or block["model"] or block["name"],
            }
        )
    return devices


def take_snapshot() -> Dict[str, Any]:
    nodes, note = read_lsblk()
    blocks = flatten_blocks(nodes)
    partsets = load_partsets()
    os_disks = os_disk_paths(blocks, partsets)
    config = load_config()
    enabled = {drive["uuid"] for drive in config["drives"]}
    return {
        "blocks": blocks,
        "devices": classify_blocks(blocks, os_disks, partsets, enabled),
        "os_disks": os_disks,
        "os_known": bool(os_disks),
        "config": config,
        "note": note,
    }


def drive_views(devices: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Toggle-list entries: every eligible drive plus enabled drives not plugged in."""
    views: List[Dict[str, Any]] = []
    present: Set[str] = set()
    for device in devices:
        if not device["eligible"]:
            continue
        present.add(device["uuid"])
        views.append(
            {
                "uuid": device["uuid"],
                "name": device["display_name"],
                "label": device["label"],
                "size": device["size"],
                "fstype": device["fstype"],
                "path": device["path"],
                "model": device["model"],
                "transport": device["transport"],
                "mountpoint": device["mountpoint"],
                "mounted": device["mounted"],
                "enabled": device["enabled"],
                "present": True,
            }
        )
    for drive in config["drives"]:
        if drive["uuid"] in present:
            continue
        views.append(
            {
                "uuid": drive["uuid"],
                "name": drive["label"] or drive["uuid"],
                "label": drive["label"],
                "size": "",
                "fstype": drive["fstype"],
                "path": "",
                "model": "",
                "transport": "",
                "mountpoint": "",
                "mounted": False,
                "enabled": True,
                "present": False,
            }
        )
    views.sort(key=lambda v: (not v["present"], v["name"].lower()))
    return views


def format_target_views(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets = [
        {
            "path": d["path"],
            "fingerprint": d["fingerprint"],
            "type": d["type"],
            "name": d["display_name"],
            "size": d["size"],
            "fstype": d["fstype"],
            "label": d["label"],
            "model": d["model"],
            "mounted": d["mounted"],
        }
        for d in devices
        if d["can_format"]
    ]
    targets.sort(key=lambda t: (t["type"] != "disk", t["path"]))
    return targets


# ----------------------------------------------------------------------- config


def _clean_drive(entry: Any) -> Optional[Dict[str, str]]:
    if not isinstance(entry, dict):
        return None
    uuid = str(entry.get("uuid") or "").strip()
    if not UUID_PATTERN.match(uuid):
        return None
    return {
        "uuid": uuid,
        "label": str(entry.get("label") or ""),
        "fstype": str(entry.get("fstype") or ""),
    }


def load_config() -> Dict[str, Any]:
    """Config v2 keeps drives by UUID. A v1 file (device path + label) comes back
    with a `legacy` key so the caller can migrate it against real devices."""
    empty: Dict[str, Any] = {"version": CONFIG_VERSION, "drives": []}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return empty
    if not isinstance(raw, dict):
        return empty
    if isinstance(raw.get("drives"), list):
        drives = [d for d in map(_clean_drive, raw["drives"]) if d]
        return {"version": CONFIG_VERSION, "drives": drives}
    if raw.get("device_path") or raw.get("label"):
        empty["legacy"] = {
            "device_path": str(raw.get("device_path") or ""),
            "label": str(raw.get("label") or ""),
        }
    return empty


def save_config(config: Dict[str, Any]) -> None:
    payload = {"version": CONFIG_VERSION, "drives": config["drives"]}
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = f"{CONFIG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    os.replace(tmp, CONFIG_PATH)


def upsert_drive(config: Dict[str, Any], device: Dict[str, Any]) -> None:
    config["drives"] = [d for d in config["drives"] if d["uuid"] != device["uuid"]]
    config["drives"].append(
        {"uuid": device["uuid"], "label": device["label"], "fstype": device["fstype"]}
    )


def migrate_legacy(config: Dict[str, Any], devices: List[Dict[str, Any]]) -> bool:
    """
    Turn a v1 config into UUID entries. The old device path is NOT trusted (it
    may now point at a different disk); we only adopt a drive that matches the old
    label, or the single Steam-library-looking drive. Returns True when the config
    changed and should be saved.
    """
    legacy = config.pop("legacy", None)
    if legacy is None:
        return False

    eligible = [d for d in devices if d["eligible"]]
    wanted = legacy.get("label", "").strip().lower()
    pick: Optional[Dict[str, Any]] = None

    by_label = [d for d in eligible if wanted and d["label"].lower() == wanted]
    if len(by_label) == 1:
        pick = by_label[0]
    if pick is None:
        libraries = [
            d
            for d in eligible
            if d["label"].lower() == "nvme1tb" or d["mountpoint"].startswith("/run/media/")
        ]
        if len(libraries) == 1:
            pick = libraries[0]

    if pick is not None:
        upsert_drive(config, pick)
    return True


# --------------------------------------------------------------------- automount


def render_udev_rules(uuids: List[str]) -> str:
    rules = "".join(UDEV_RULE_TEMPLATE.format(uuid=u, helper=HELPER_PATH) for u in uuids)
    return f'{UDEV_RULES_HEADER}\n{rules}\nLABEL="map_storage_end"\n'


def render_service(uuids: List[str]) -> str:
    return SERVICE_TEMPLATE.format(helper=HELPER_PATH, uuids=" ".join(uuids))


def render_helper(user: str) -> str:
    return HELPER_TEMPLATE.replace("@DECK_USER@", user)


def write_if_changed(path: str, content: str, mode: int) -> bool:
    try:
        with open(path, encoding="utf-8") as file:
            if file.read() == content and (os.stat(path).st_mode & 0o777) == mode:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        file.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    return True


def remove_file(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return run([tool("systemctl"), *args])


def cleanup_legacy(logs: List[str]) -> None:
    """Retire pieces installed by plugin <= 0.1.x (label-based units)."""
    if os.path.isfile(LEGACY_SERVICE_PATH):
        systemctl("disable", LEGACY_SERVICE_NAME)
        systemctl("stop", LEGACY_SERVICE_NAME)
        logs.append(f"disabled legacy {LEGACY_SERVICE_NAME}")
    if remove_file(LEGACY_HELPER_PATH):
        logs.append(f"removed legacy {LEGACY_HELPER_PATH}")


def install_automount(uuids: List[str], logs: List[str]) -> None:
    """Make the udev rule, mount helper and boot unit match the enabled drives."""
    if not uuids:
        remove_automount(logs)
        return

    rules_changed = write_if_changed(UDEV_RULE_PATH, render_udev_rules(uuids), 0o644)
    helper_changed = write_if_changed(HELPER_PATH, render_helper(deck_user()), 0o755)
    unit_changed = write_if_changed(SERVICE_PATH, render_service(uuids), 0o644)

    if rules_changed:
        run([tool("udevadm"), "control", "--reload-rules"])
    if unit_changed:
        systemctl("daemon-reload")
    if out(systemctl("is-enabled", SERVICE_NAME)) != "enabled":
        systemctl("enable", SERVICE_NAME)
        logs.append(f"enabled {SERVICE_NAME}")
    if rules_changed or helper_changed or unit_changed:
        logs.append("updated udev rule, mount helper and boot unit")


def remove_automount(logs: List[str]) -> None:
    had_unit = os.path.isfile(SERVICE_PATH)
    if had_unit:
        systemctl("disable", SERVICE_NAME)
    removed = [remove_file(p) for p in (SERVICE_PATH, UDEV_RULE_PATH, HELPER_PATH)]
    try:
        os.rmdir(ETC_DIR)
    except OSError:
        pass
    if any(removed):
        systemctl("daemon-reload")
        run([tool("udevadm"), "control", "--reload-rules"])
        logs.append("removed automount rule, mount helper and boot unit")


def mount_target(source: str) -> str:
    result = run([tool("findmnt"), "-no", "TARGET", source])
    return out(result).splitlines()[0] if result.returncode == 0 and out(result) else ""


def mount_target_for_uuid(uuid: str) -> str:
    return mount_target(f"UUID={uuid}") if UUID_PATTERN.match(uuid) else ""


def mount_drives(uuids: List[str], wait: int, logs: List[str]) -> Dict[str, str]:
    """Mount through the helper (UUID based) and report each drive's mount point."""
    if not uuids:
        return {}
    if not os.path.isfile(HELPER_PATH):
        logs.append("mount helper missing")
        return {}
    result = run([HELPER_PATH, "--wait", str(wait), *uuids], timeout=60)
    for line in (result.stdout or "").splitlines():
        logs.append(line.strip())
    if result.returncode != 0 and err(result):
        logs.append(err(result))
    return {uuid: mount_target_for_uuid(uuid) for uuid in uuids}


def ensure_steam_layout(mount_at: str, label: str, logs: List[str]) -> None:
    uid, gid = deck_ids()
    steamapps = os.path.join(mount_at, "steamapps")
    if not os.path.isdir(steamapps):
        for relative in (
            "steamapps/common",
            "steamapps/downloading",
            "steamapps/temp",
            "steamapps/shadercache",
        ):
            os.makedirs(os.path.join(mount_at, relative), exist_ok=True)
        for root, dirs, files in os.walk(steamapps):
            for name in [root, *[os.path.join(root, n) for n in (*dirs, *files)]]:
                os.chown(name, uid, gid)
        logs.append("created steamapps folder structure")

    vdf_path = os.path.join(mount_at, "libraryfolder.vdf")
    if not os.path.isfile(vdf_path):
        content_id = random.SystemRandom().randrange(10**18, 10**19)
        with open(vdf_path, "w", encoding="utf-8") as file:
            file.write(
                '"libraryfolder"\n{\n'
                f'\t"contentid"\t\t"{content_id}"\n'
                f'\t"label"\t\t"{label}"\n'
                "}\n"
            )
        os.chmod(vdf_path, 0o644)
        os.chown(vdf_path, uid, gid)
        logs.append("created libraryfolder.vdf")


def unmount_if_idle(source: str, logs: List[str]) -> bool:
    """Plain umount: refuses when busy instead of yanking files from a running game."""
    target = mount_target(source)
    if not target:
        return True
    result = run([tool("umount"), target])
    if result.returncode == 0:
        logs.append(f"unmounted {target}")
        if target.startswith(f"/run/media/{deck_user()}/"):
            try:
                os.rmdir(target)
            except OSError:
                pass
        return True
    logs.append(f"could not unmount {target}: {err(result)}")
    return False


# ----------------------------------------------------------------------- plugin


def service_state() -> Dict[str, Any]:
    return {
        "enabled": out(systemctl("is-enabled", SERVICE_NAME)) or "unknown",
        "active": out(systemctl("is-active", SERVICE_NAME)) or "unknown",
        "has_udev_rule": os.path.isfile(UDEV_RULE_PATH),
        "has_helper": os.path.isfile(HELPER_PATH),
        "has_unit": os.path.isfile(SERVICE_PATH),
    }


def find_eligible(snapshot: Dict[str, Any], uuid: str) -> Dict[str, Any]:
    for device in snapshot["devices"]:
        if device["uuid"] == uuid and device["eligible"]:
            return device
    raise RuntimeError(
        "drive not found or not usable (system disks and unsupported filesystems are excluded)"
    )


class Plugin:
    _heal_task: Optional["asyncio.Task[None]"] = None

    def _require_root(self) -> None:
        if os.getuid() != 0:
            raise RuntimeError("backend is not running as root; reinstall the plugin and restart Decky")

    def _apply_config(self, config: Dict[str, Any], logs: List[str]) -> List[str]:
        """Install (or remove) automount so it matches the config; return enabled UUIDs."""
        uuids = [d["uuid"] for d in config["drives"]]
        install_automount(uuids, logs)
        return uuids

    def _scan_payload(self) -> Dict[str, Any]:
        snapshot = take_snapshot()
        devices = snapshot["devices"]
        error = ""
        if not devices:
            error = "no storage devices found. Check plugin logs under homebrew/logs."
        elif not snapshot["os_known"]:
            error = "could not tell which disk holds SteamOS; drives are hidden for safety."
        return {
            "ok": not error,
            "error": error,
            "debug": (
                f"plugin {getattr(decky, 'DECKY_PLUGIN_VERSION', '?')}; "
                f"devices {len(devices)}; os_disks {sorted(snapshot['os_disks'])}; {snapshot['note']}"
            ).strip("; "),
            "count": len(devices),
            "drives": drive_views(devices, snapshot["config"]),
            "format_targets": format_target_views(devices),
            "service": service_state(),
            "os_known": snapshot["os_known"],
        }

    def _set_drive_enabled(self, uuid: str, enabled: bool) -> Dict[str, Any]:
        logs: List[str] = []
        errors: List[str] = []
        mount_at = ""
        try:
            self._require_root()
            uuid = validate_uuid(uuid)
            with _LOCK:
                snapshot = take_snapshot()
                config = snapshot["config"]
                if enabled:
                    device = find_eligible(snapshot, uuid)
                    upsert_drive(config, device)
                    save_config(config)
                    cleanup_legacy(logs)
                    self._apply_config(config, logs)
                    mount_at = mount_drives([uuid], 10, logs).get(uuid, "")
                    if mount_at:
                        ensure_steam_layout(mount_at, device["label"] or uuid, logs)
                        logs.append(f"mounted at {mount_at}")
                    else:
                        errors.append("enabled, but the drive could not be mounted right now")
                else:
                    config["drives"] = [d for d in config["drives"] if d["uuid"] != uuid]
                    save_config(config)
                    self._apply_config(config, logs)
                    if not unmount_if_idle(f"UUID={uuid}", logs):
                        errors.append("disabled, but the drive is in use and stays mounted until reboot")
            return {
                "ok": not errors,
                "uuid": uuid,
                "enabled": enabled,
                "mount_target": mount_at,
                "logs": logs,
                "errors": errors,
            }
        except Exception as exc:
            decky.logger.exception("set_drive_enabled failed")
            errors.append(str(exc))
            return {"ok": False, "uuid": uuid, "enabled": enabled, "logs": logs, "errors": errors}

    def _self_heal(self) -> Dict[str, Any]:
        """
        Re-apply the saved setup. SteamOS updates and plugin reinstalls can drop the
        udev rule / boot unit, and a v1 config has to be migrated to UUIDs. Safe to
        run any number of times.
        """
        logs: List[str] = []
        errors: List[str] = []
        try:
            self._require_root()
            with _LOCK:
                snapshot = take_snapshot()
                config = snapshot["config"]
                if migrate_legacy(config, snapshot["devices"]):
                    save_config(config)
                    logs.append(f"migrated legacy config -> {len(config['drives'])} drive(s)")
                cleanup_legacy(logs)

                by_uuid = {d["uuid"]: d for d in snapshot["devices"]}
                unusable = [
                    d["uuid"]
                    for d in config["drives"]
                    if d["uuid"] in by_uuid and not by_uuid[d["uuid"]]["eligible"]
                ]
                if unusable and snapshot["os_known"]:
                    config["drives"] = [d for d in config["drives"] if d["uuid"] not in unusable]
                    save_config(config)
                    logs.append(f"dropped {len(unusable)} drive(s) that are not usable anymore")

                uuids = self._apply_config(config, logs)
                for uuid, mount_at in mount_drives(uuids, 10, logs).items():
                    if mount_at:
                        label = by_uuid.get(uuid, {}).get("label") or uuid
                        ensure_steam_layout(mount_at, label, logs)
                    else:
                        errors.append(f"{uuid} not mounted")
            decky.logger.info("map-storage self-heal: %s", "; ".join(logs) or "nothing to do")
            return {"ok": not errors, "logs": logs, "errors": errors}
        except Exception as exc:
            decky.logger.exception("map-storage self-heal failed")
            errors.append(str(exc))
            return {"ok": False, "logs": logs, "errors": errors}

    def _format_storage(
        self, device_path: str, fingerprint_value: str, label: str, enable: bool
    ) -> Dict[str, Any]:
        logs: List[str] = []
        errors: List[str] = []
        try:
            self._require_root()
            label = validate_label(label)
            device_path = validate_device_path(device_path)
            with _LOCK:
                snapshot = take_snapshot()
                target = next((d for d in snapshot["devices"] if d["path"] == device_path), None)
                if target is None:
                    raise RuntimeError(f"{device_path} not found; rescan and try again")
                if target["fingerprint"] != fingerprint_value:
                    raise RuntimeError(
                        f"{device_path} is not the drive you selected (device names change "
                        "between boots); rescan and try again"
                    )
                if not target["can_format"]:
                    raise RuntimeError("refusing to format a system device")

                affected = [
                    b
                    for b in snapshot["blocks"]
                    if b["path"] == device_path or b["disk"] == device_path
                ]
                for block in affected:
                    if block["mountpoints"] and not unmount_if_idle(block["path"], logs):
                        raise RuntimeError(f"{block['path']} is in use; close Steam games and retry")

                wiped = {b["uuid"] for b in affected if b["uuid"]}
                config = snapshot["config"]
                config["drives"] = [d for d in config["drives"] if d["uuid"] not in wiped]

                if target["type"] == "part":
                    partition = device_path
                else:
                    run([tool("wipefs"), "-af", device_path])
                    parted = run(
                        [
                            tool("parted"), "-s", device_path,
                            "mklabel", "gpt", "mkpart", "primary", "ext4", "1MiB", "100%",
                        ]
                    )
                    if parted.returncode != 0:
                        raise RuntimeError(f"parted failed: {err(parted)}")
                    run([tool("partprobe"), device_path])
                    run([tool("udevadm"), "settle", "--timeout=10"])
                    partition = self._first_partition(device_path)
                    logs.append(f"created partition {partition}")

                mkfs = run([tool("mkfs.ext4"), "-F", "-L", label, partition], timeout=300)
                if mkfs.returncode != 0:
                    raise RuntimeError(f"mkfs.ext4 failed: {err(mkfs)}")
                run([tool("udevadm"), "settle", "--timeout=10"])
                logs.append(f"formatted {partition} as ext4 ({label})")

                uuid = out(run([tool("blkid"), "-s", "UUID", "-o", "value", partition]))
                mount_at = ""
                if enable and uuid:
                    upsert_drive(config, {"uuid": uuid, "label": label, "fstype": "ext4"})
                    save_config(config)
                    cleanup_legacy(logs)
                    self._apply_config(config, logs)
                    mount_at = mount_drives([uuid], 10, logs).get(uuid, "")
                    if mount_at:
                        ensure_steam_layout(mount_at, label, logs)
                        logs.append(f"mounted at {mount_at}")
                    else:
                        errors.append("formatted, but the drive could not be mounted right now")
                else:
                    save_config(config)
                    self._apply_config(config, logs)
            return {
                "ok": not errors,
                "label": label,
                "uuid": uuid,
                "partition": partition,
                "mount_target": mount_at,
                "logs": logs,
                "errors": errors,
            }
        except Exception as exc:
            decky.logger.exception("format_storage failed")
            errors.append(str(exc))
            return {"ok": False, "label": label, "logs": logs, "errors": errors}

    def _first_partition(self, disk_path: str) -> str:
        for _ in range(10):
            nodes, _note = read_lsblk()
            for block in flatten_blocks(nodes):
                if block["disk"] == disk_path and block["type"] == "part":
                    return block["path"]
            run(["/bin/sleep", "1"])
        raise RuntimeError("partition not found after partitioning")

    def _service_logs(self, lines: int) -> str:
        count = str(max(20, min(int(lines), 300)))
        result = run(
            [tool("journalctl"), "-b", "-t", "map-storage-mount.sh", "-n", count, "--no-pager"]
        )
        return (out(result) or err(result)).strip()

    async def ping(self) -> Dict[str, str]:
        return {
            "status": "ok",
            "version": getattr(decky, "DECKY_PLUGIN_VERSION", "unknown"),
            "user": deck_user(),
            "is_root": str(os.getuid() == 0).lower(),
            "euid": str(os.getuid()),
        }

    async def list_storage_devices(self) -> str:
        """JSON string (reliable through the Decky bridge): drives, format_targets, service."""
        try:
            payload = await asyncio.to_thread(self._scan_payload)
            decky.logger.info("list_storage_devices: %s devices", payload["count"])
            return json.dumps(payload)
        except Exception as exc:
            decky.logger.exception("list_storage_devices failed")
            return json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "debug": "",
                    "count": 0,
                    "drives": [],
                    "format_targets": [],
                    "service": {},
                    "os_known": False,
                }
            )

    async def set_drive_enabled(self, uuid: str, enabled: bool) -> Dict[str, Any]:
        return await asyncio.to_thread(self._set_drive_enabled, uuid, bool(enabled))

    async def format_storage(
        self, device_path: str, fingerprint: str, label: str, enable: bool
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._format_storage, device_path, fingerprint, label, bool(enable)
        )

    async def reapply_now(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._self_heal)

    async def get_service_logs(self, lines: int = 80) -> str:
        return await asyncio.to_thread(self._service_logs, lines)

    async def _self_heal_task(self) -> None:
        try:
            await asyncio.to_thread(self._self_heal)
        except Exception:
            decky.logger.exception("map-storage self-heal crashed on load")

    async def _main(self):
        decky.logger.info("map-storage backend loaded")
        self._heal_task = asyncio.get_running_loop().create_task(self._self_heal_task())

    async def _unload(self):
        decky.logger.info("map-storage backend unloaded")

    async def _uninstall(self):
        decky.logger.info("map-storage backend uninstalled")

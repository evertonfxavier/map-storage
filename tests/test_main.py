import copy
import json
import logging
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "lsblk_nvme_internal_first.json")

_stub = types.ModuleType("decky")
_stub.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="map-storage-test-")
_stub.DECKY_USER = "deck"
_stub.DECKY_USER_HOME = "/home/deck"
_stub.DECKY_PLUGIN_VERSION = "test"
_stub.logger = logging.getLogger("decky-stub")
sys.modules["decky"] = _stub
sys.path.insert(0, ROOT)

import main  # noqa: E402

LIBRARY_UUID = "425d7bd7-b964-08d7-84fc-288d7d9899ec"


def lsblk_nodes(swapped: bool = False, mounted: bool = True):
    """The real Deck layout. `swapped` reproduces the boot where nvme0/nvme1 trade places."""
    raw = read(FIXTURE)
    if swapped:
        raw = raw.replace("nvme0", "@@").replace("nvme1", "nvme0").replace("@@", "nvme1")
    nodes = json.loads(raw)["blockdevices"]
    if not mounted:
        for node in main_walk(nodes):
            if node.get("label") == "NVMe1TB":
                node["mountpoints"] = []
    return nodes


def read(path):
    with open(path, encoding="utf-8") as file:
        return file.read()


def main_walk(nodes):
    for node in nodes:
        yield node
        yield from main_walk(node.get("children") or [])


def snapshot_for(nodes, partsets=frozenset(), enabled=()):
    blocks = main.flatten_blocks(nodes)
    os_disks = main.os_disk_paths(blocks, set(partsets))
    devices = main.classify_blocks(blocks, os_disks, set(partsets), set(enabled))
    return blocks, os_disks, devices


class DeviceClassificationTest(unittest.TestCase):
    def check_layout(self, swapped: bool):
        library_disk = "/dev/nvme0n1" if swapped else "/dev/nvme1n1"
        internal_disk = "/dev/nvme1n1" if swapped else "/dev/nvme0n1"
        _, os_disks, devices = snapshot_for(lsblk_nodes(swapped))

        self.assertEqual(os_disks, {internal_disk})
        eligible = [d for d in devices if d["eligible"]]
        self.assertEqual([d["uuid"] for d in eligible], [LIBRARY_UUID])
        self.assertTrue(eligible[0]["path"].startswith(library_disk))

        for device in devices:
            if device["disk"] == internal_disk:
                self.assertTrue(device["is_system"], device["path"])
                self.assertFalse(device["eligible"], device["path"])
                self.assertFalse(device["can_format"], device["path"])

    def test_internal_disk_found_when_it_is_nvme0(self):
        self.check_layout(swapped=False)

    def test_internal_disk_found_when_it_is_nvme1(self):
        self.check_layout(swapped=True)

    def test_esp_is_never_eligible_even_if_its_label_is_requested(self):
        for swapped in (False, True):
            _, _, devices = snapshot_for(lsblk_nodes(swapped))
            esp = next(d for d in devices if d["label"] == "esp")
            self.assertTrue(esp["is_system"])
            self.assertFalse(esp["eligible"])
            self.assertNotIn(esp["path"], [t["path"] for t in main.format_target_views(devices)])

    def test_unmounted_library_is_still_eligible(self):
        _, _, devices = snapshot_for(lsblk_nodes(mounted=False))
        library = next(d for d in devices if d["uuid"] == LIBRARY_UUID)
        self.assertTrue(library["eligible"])
        self.assertFalse(library["mounted"])

    def test_unknown_os_disk_hides_every_drive(self):
        nodes = lsblk_nodes()
        for node in main_walk(nodes):
            node["mountpoints"] = []
        _, os_disks, devices = snapshot_for(nodes)
        self.assertEqual(os_disks, set())
        self.assertFalse(any(d["eligible"] or d["can_format"] for d in devices))

    def test_partsets_mark_a_disk_as_system(self):
        nodes = lsblk_nodes()
        for node in main_walk(nodes):
            node["mountpoints"] = []
        rootfs = next(n for n in main_walk(nodes) if n.get("label") == "rootfs")
        _, os_disks, devices = snapshot_for(nodes, partsets={rootfs["partuuid"]})
        self.assertEqual(os_disks, {"/dev/nvme0n1"})
        self.assertEqual([d["uuid"] for d in devices if d["eligible"]], [LIBRARY_UUID])

    def test_swap_and_loop_devices_are_ignored(self):
        _, _, devices = snapshot_for(lsblk_nodes())
        self.assertFalse([d for d in devices if d["name"].startswith("zram")])

    def test_whole_disk_with_partitions_is_not_a_mountable_drive(self):
        _, _, devices = snapshot_for(lsblk_nodes())
        disk = next(d for d in devices if d["path"] == "/dev/nvme1n1")
        self.assertFalse(disk["eligible"])
        self.assertTrue(disk["can_format"])

    def test_fingerprint_differs_between_media(self):
        _, _, devices = snapshot_for(lsblk_nodes())
        self.assertEqual(len({d["fingerprint"] for d in devices}), len(devices))

    def test_drive_views_lists_enabled_drive_that_is_unplugged(self):
        _, _, devices = snapshot_for(lsblk_nodes(), enabled=[LIBRARY_UUID])
        config = {
            "drives": [
                {"uuid": LIBRARY_UUID, "label": "NVMe1TB", "fstype": "ext4"},
                {"uuid": "AAAA-BBBB", "label": "USBSTICK", "fstype": "ext4"},
            ]
        }
        views = main.drive_views(devices, config)
        self.assertEqual([v["uuid"] for v in views], [LIBRARY_UUID, "AAAA-BBBB"])
        self.assertTrue(views[0]["present"] and views[0]["enabled"] and views[0]["mounted"])
        self.assertFalse(views[1]["present"])
        self.assertTrue(views[1]["enabled"])


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="map-storage-cfg-")
        patcher = mock.patch.object(main, "CONFIG_PATH", os.path.join(self.dir, "config.json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, payload):
        with open(main.CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(payload, file)

    def test_missing_file_is_empty_v2(self):
        self.assertEqual(main.load_config(), {"version": 2, "drives": []})

    def test_v2_round_trip_and_invalid_entries_dropped(self):
        self.write(
            {
                "version": 2,
                "drives": [
                    {"uuid": LIBRARY_UUID, "label": "NVMe1TB", "fstype": "ext4"},
                    {"uuid": "../etc/passwd", "label": "x"},
                    "junk",
                ],
            }
        )
        config = main.load_config()
        self.assertEqual([d["uuid"] for d in config["drives"]], [LIBRARY_UUID])
        main.save_config(config)
        self.assertEqual(main.load_config(), config)

    def test_v1_config_is_reported_as_legacy(self):
        self.write({"device_path": "/dev/nvme1n1p1", "label": "SteamLibrary", "format_on_apply": False})
        config = main.load_config()
        self.assertEqual(config["drives"], [])
        self.assertEqual(config["legacy"]["device_path"], "/dev/nvme1n1p1")

    def test_corrupt_file_is_empty(self):
        with open(main.CONFIG_PATH, "w", encoding="utf-8") as file:
            file.write("{not json")
        self.assertEqual(main.load_config(), {"version": 2, "drives": []})

    def test_legacy_stale_path_pointing_at_esp_adopts_the_real_library(self):
        # the exact field case: saved /dev/nvme1n1p1 + label SteamLibrary, but nvme1
        # is now the SteamOS disk and the library moved to nvme0
        _, _, devices = snapshot_for(lsblk_nodes(swapped=True))
        config = {
            "version": 2,
            "drives": [],
            "legacy": {"device_path": "/dev/nvme1n1p1", "label": "SteamLibrary"},
        }
        self.assertTrue(main.migrate_legacy(config, devices))
        self.assertNotIn("legacy", config)
        self.assertEqual([d["uuid"] for d in config["drives"]], [LIBRARY_UUID])

    def test_legacy_label_match_wins(self):
        _, _, devices = snapshot_for(lsblk_nodes())
        config = {"drives": [], "legacy": {"device_path": "", "label": "nvme1tb"}}
        main.migrate_legacy(config, devices)
        self.assertEqual([d["uuid"] for d in config["drives"]], [LIBRARY_UUID])

    def test_legacy_ambiguous_drives_adopt_nothing(self):
        nodes = lsblk_nodes()
        extra = copy.deepcopy(next(n for n in main_walk(nodes) if n.get("label") == "NVMe1TB"))
        extra.update({"path": "/dev/sda1", "name": "sda1", "uuid": "11111111-2222-3333-4444-555555555555",
                      "label": "GAMES", "mountpoints": ["/run/media/deck/GAMES"]})
        nodes.append({"name": "sda", "path": "/dev/sda", "type": "disk", "size": "1T", "children": [extra],
                      "mountpoints": []})
        _, _, devices = snapshot_for(nodes)
        config = {"drives": [], "legacy": {"device_path": "", "label": "SteamLibrary"}}
        self.assertTrue(main.migrate_legacy(config, devices))
        self.assertEqual(config["drives"], [])

    def test_no_legacy_key_means_no_change(self):
        self.assertFalse(main.migrate_legacy({"drives": []}, []))


class RenderTest(unittest.TestCase):
    def test_udev_rule_matches_by_uuid_not_label(self):
        rules = main.render_udev_rules([LIBRARY_UUID])
        self.assertIn(f'ENV{{ID_FS_UUID}}=="{LIBRARY_UUID}"', rules)
        self.assertIn(f"{main.HELPER_PATH} --wait 5 {LIBRARY_UUID}", rules)
        self.assertNotIn("ID_FS_LABEL", rules)
        self.assertIn('LABEL="map_storage_end"', rules)

    def test_service_runs_before_the_display_manager(self):
        unit = main.render_service([LIBRARY_UUID, "AAAA-BBBB"])
        self.assertIn("Before=sddm.service", unit)
        self.assertIn(f"ExecStart={main.HELPER_PATH} --wait 10 {LIBRARY_UUID} AAAA-BBBB", unit)

    def test_helper_is_valid_bash_and_has_no_template_leftovers(self):
        script = main.render_helper("deck")
        self.assertNotIn("@DECK_USER@", script)
        self.assertIn('DECK_USER="deck"', script)
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as file:
            file.write(script)
        self.addCleanup(os.remove, file.name)
        result = subprocess.run(["bash", "-n", file.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_helper_rejects_invalid_uuid_without_touching_anything(self):
        script = main.render_helper("root")
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as file:
            file.write(script.replace("/run/map-storage-mount.lock", "/tmp/map-storage-test.lock"))
        self.addCleanup(os.remove, file.name)
        os.chmod(file.name, 0o755)
        result = subprocess.run([file.name, "../../etc"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid uuid", result.stdout)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="map-storage-etc-")
        self.calls = []
        for name, value in (
            ("ETC_DIR", os.path.join(self.dir, "map-storage")),
            ("HELPER_PATH", os.path.join(self.dir, "map-storage", "map-storage-mount.sh")),
            ("UDEV_RULE_PATH", os.path.join(self.dir, "rules", "99-map-storage-automount.rules")),
            ("SERVICE_PATH", os.path.join(self.dir, "system", "map-storage-automount.service")),
        ):
            patcher = mock.patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        def fake_run(args, timeout=45):
            self.calls.append(list(args))
            stdout = "disabled\n" if "is-enabled" in args else ""
            return subprocess.CompletedProcess(args, 0, stdout, "")

        patcher = mock.patch.object(main, "run", fake_run)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ran(self, *needle):
        return any(all(part in call for part in needle) for call in self.calls)

    def test_install_writes_files_and_is_idempotent(self):
        logs = []
        main.install_automount([LIBRARY_UUID], logs)
        for path in (main.UDEV_RULE_PATH, main.HELPER_PATH, main.SERVICE_PATH):
            self.assertTrue(os.path.isfile(path), path)
        self.assertEqual(os.stat(main.HELPER_PATH).st_mode & 0o777, 0o755)
        self.assertTrue(self.ran("daemon-reload"))
        self.assertTrue(self.ran("--reload-rules"))
        self.assertTrue(self.ran("enable", main.SERVICE_NAME))

        self.calls.clear()
        main.install_automount([LIBRARY_UUID], [])
        self.assertFalse(self.ran("daemon-reload"))
        self.assertFalse(self.ran("--reload-rules"))

    def test_changing_enabled_drives_rewrites_rule_and_unit(self):
        main.install_automount([LIBRARY_UUID], [])
        self.calls.clear()
        main.install_automount([LIBRARY_UUID, "AAAA-BBBB"], [])
        self.assertIn("AAAA-BBBB", read(main.UDEV_RULE_PATH))
        self.assertTrue(self.ran("daemon-reload"))

    def test_disabling_the_last_drive_removes_everything(self):
        main.install_automount([LIBRARY_UUID], [])
        logs = []
        main.install_automount([], logs)
        for path in (main.UDEV_RULE_PATH, main.HELPER_PATH, main.SERVICE_PATH):
            self.assertFalse(os.path.exists(path), path)
        self.assertTrue(self.ran("disable", main.SERVICE_NAME))
        self.assertFalse(os.path.exists(main.ETC_DIR))


class PluginGuardTest(unittest.TestCase):
    """The backend must refuse dangerous requests on its own, whatever the UI sends."""

    def setUp(self):
        self.plugin = main.Plugin()
        self.dir = tempfile.mkdtemp(prefix="map-storage-guard-")
        for name, value in (
            ("CONFIG_PATH", os.path.join(self.dir, "config.json")),
            ("HELPER_PATH", os.path.join(self.dir, "helper.sh")),
            ("UDEV_RULE_PATH", os.path.join(self.dir, "rules")),
            ("SERVICE_PATH", os.path.join(self.dir, "unit")),
        ):
            patcher = mock.patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.commands = []

        def fake_run(args, timeout=45):
            self.commands.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        for patcher in (
            mock.patch.object(main, "run", fake_run),
            mock.patch.object(main.os, "getuid", return_value=0),
            mock.patch.object(main, "read_lsblk", lambda: (lsblk_nodes(swapped=True), "")),
            mock.patch.object(main, "load_partsets", lambda: set()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def format_args(self, path):
        _, _, devices = snapshot_for(lsblk_nodes(swapped=True))
        device = next(d for d in devices if d["path"] == path)
        return path, device["fingerprint"]

    def test_format_refuses_the_steamos_disk(self):
        path, fp = self.format_args("/dev/nvme1n1")
        result = self.plugin._format_storage(path, fp, "SteamLibrary", False)
        self.assertFalse(result["ok"])
        self.assertIn("system", result["errors"][0])
        self.assertEqual(self.commands, [])

    def test_format_refuses_the_esp_partition(self):
        path, fp = self.format_args("/dev/nvme1n1p1")
        result = self.plugin._format_storage(path, fp, "SteamLibrary", False)
        self.assertFalse(result["ok"])
        self.assertEqual(self.commands, [])

    def test_format_refuses_when_the_path_now_points_at_other_media(self):
        _, fp = self.format_args("/dev/nvme0n1p1")
        result = self.plugin._format_storage("/dev/nvme1n1p1", fp, "SteamLibrary", False)
        self.assertFalse(result["ok"])
        self.assertIn("not the drive you selected", result["errors"][0])
        self.assertEqual(self.commands, [])

    def test_enable_refuses_a_system_partition_uuid(self):
        _, _, devices = snapshot_for(lsblk_nodes(swapped=True))
        esp = next(d for d in devices if d["label"] == "esp")
        result = self.plugin._set_drive_enabled(esp["uuid"], True)
        self.assertFalse(result["ok"])
        self.assertEqual(main.load_config()["drives"], [])

    def test_enable_rejects_malformed_uuid(self):
        result = self.plugin._set_drive_enabled("x; rm -rf /", True)
        self.assertFalse(result["ok"])
        self.assertEqual(self.commands, [])

    def test_enable_then_disable_library_updates_config(self):
        with mock.patch.object(main, "mount_drives", lambda uuids, wait, logs: {u: "/run/media/deck/NVMe1TB" for u in uuids}), \
                mock.patch.object(main, "ensure_steam_layout", lambda *a: None), \
                mock.patch.object(main, "unmount_if_idle", lambda source, logs: True):
            enabled = self.plugin._set_drive_enabled(LIBRARY_UUID, True)
            self.assertTrue(enabled["ok"], enabled)
            self.assertEqual([d["uuid"] for d in main.load_config()["drives"]], [LIBRARY_UUID])
            self.assertIn(LIBRARY_UUID, read(main.UDEV_RULE_PATH))

            disabled = self.plugin._set_drive_enabled(LIBRARY_UUID, False)
            self.assertTrue(disabled["ok"], disabled)
            self.assertEqual(main.load_config()["drives"], [])
            self.assertFalse(os.path.exists(main.UDEV_RULE_PATH))

    def test_self_heal_migrates_legacy_config_and_never_adopts_esp(self):
        with open(main.CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump({"device_path": "/dev/nvme1n1p1", "label": "esp"}, file)
        with mock.patch.object(main, "mount_drives", lambda uuids, wait, logs: {u: "/mnt" for u in uuids}), \
                mock.patch.object(main, "ensure_steam_layout", lambda *a: None):
            result = self.plugin._self_heal()
        drives = main.load_config()["drives"]
        self.assertTrue(result["ok"], result)
        self.assertEqual([d["uuid"] for d in drives], [LIBRARY_UUID])

    def test_not_root_is_reported(self):
        with mock.patch.object(main.os, "getuid", return_value=1000):
            result = self.plugin._set_drive_enabled(LIBRARY_UUID, True)
        self.assertFalse(result["ok"])
        self.assertIn("root", result["errors"][0])


if __name__ == "__main__":
    unittest.main()

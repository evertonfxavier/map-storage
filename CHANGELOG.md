# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.7] - 2026-06-20

### Fixed

- Device dropdown now keeps the disk you pick: the load effect ran on every selection change, re-scanning and reverting your choice.
- Repeating toast popups: automatic scans (on open and after actions) no longer raise toasts; only manual "Rescan" does.
- Selection is preserved across rescans when the device is still present; auto-pick only happens when there is no valid selection.

## [0.1.6] - 2026-06-20

### Fixed

- **Survives SteamOS updates:** the plugin now self-heals on every load. SteamOS uses an immutable A/B root, so OS updates wipe `/etc` and `/usr/local` (udev rule, mount script, systemd unit). On boot the plugin re-creates them from the saved config and mounts the configured library automatically.

### Added

- `reapply_now` backend method and **"Re-apply after system update"** button to manually restore the automount setup.

## [0.1.5] - 2026-05-26

### Fixed

- NVMe layout detection uses the disk that mounts `/` as internal (not hardcoded `nvme0` = system).
- Auto-select prefers label **NVMe1TB** and `/dev/nvme0n1p*` expansion (fixes Decks where expansion is `nvme0` and SteamOS is `nvme1`).

### Added

- `is_expansion` flag and **EXPANSION** badge in the device list.

## [0.1.4] - 2026-05-26

### Fixed

- Subprocess runs with a clean environment and `/bin/bash -c` to avoid `/bin/sh: symbol lookup error` on SteamOS.
- Storage scan enriches every device via `blkid`, `findmnt`, and `lsblk` (no more bare `proc · ? · no-fs` entries).
- Automount uses `runuser` and full paths (`/usr/bin/udisksctl`, etc.) instead of `sudo` in the mount script.
- `apply_storage_fix` requires a partition (not whole disk) unless formatting; uses the partition’s real ext4 label (e.g. `NVMe1TB`).
- Status and setup resolve label from the selected partition when the text field still says `SteamLibrary`.
- Attempts immediate `udisksctl` mount after configuring the systemd service.

### Changed

- Internal `nvme0n1` devices are marked SYSTEM; auto-select prefers mounted `nvme1` / Steam library partitions.
- UI syncs label when changing device; blocks whole-disk configure without format.
- Storage label shown in device list, selection summary, and status (filesystem LABEL or Steam library folder name).

## [0.1.3] - 2026-05-26

### Fixed

- Storage scan returns JSON string for reliable Decky frontend parsing (fixes empty dropdown).
- Prioritize `/run/media/deck/*` and `findmnt` so mounted libraries (e.g. NVMe1TB) always appear.
- Explicit PATH and tool resolution for `lsblk`/`findmnt`/`blkid` on SteamOS.

### Added

- Loading spinner, scan status banner, and toasts on every scan/action.
- Backend `ping` health check on plugin open.
- Scan debug output shown in UI when no devices are found.

## [0.1.2] - 2026-05-26

### Fixed

- Storage scan on Steam Deck: fallback when `lsblk` columns fail; also discover drives via `findmnt` and `blkid` (e.g. `/run/media/deck/NVMe1TB`).
- Devices mounted under `/run/media/` are no longer marked as system disks.
- UI shows scan debug info when no devices are found; auto-suggests label `NVMe1TB` when detected.

## [0.1.1] - 2026-05-26

### Added

- Support for all plugged storage: NVMe, USB, SD/mmc, SATA (`sd*`), VirtIO/IDE.
- Device list shows transport, model, and system-disk protection.

### Changed

- udev automount rule applies to any block device with matching filesystem label (not NVMe-only).
- UI copy updated for generic storage selection.

### Fixed

- GitHub Actions pnpm setup (use `packageManager` from `package.json` only).

## [0.1.0] - 2026-05-26

### Added

- Initial Map Storage plugin: storage setup UI, format toggle, automount fix for Steam Game Mode.
- GitHub Actions CI and release workflow with downloadable ZIPs.

[Unreleased]: https://github.com/evertonfxavier/map-storage/compare/v0.1.7...HEAD
[0.1.7]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.7
[0.1.6]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.6
[0.1.5]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.5
[0.1.4]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.4
[0.1.3]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.3
[0.1.2]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.2
[0.1.1]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.1
[0.1.0]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.0

# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/evertonfxavier/map-storage/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.1
[0.1.0]: https://github.com/evertonfxavier/map-storage/releases/tag/v0.1.0

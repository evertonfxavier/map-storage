# Map Storage

[![Build plugin](https://github.com/evertonfxavier/map-storage/actions/workflows/build-plugin.yml/badge.svg)](https://github.com/evertonfxavier/map-storage/actions/workflows/build-plugin.yml)

Decky Loader plugin for **Steam Deck** that helps set up **any plugged storage** for Steam library storage:

- scan disks/partitions (NVMe, USB, SD card, SATA, etc.)
- optional **format** (ext4 + custom label)
- **automount via udisks2** so Game Mode can discover the drive (same idea as manual fix scripts)
- create `steamapps` layout and `libraryfolder.vdf` when needed

> **Warning:** formatting erases all data on the selected drive. Double-check the device in the dropdown before confirming.

## Prerequisites

- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) installed on your Steam Deck
- Any supported block device (NVMe, USB flash/HDD, microSD, SATA SSD, …)
- This plugin requests **`_root`** — it writes udev/systemd files under `/etc` and `/usr/local/bin`

## Installation

### From GitHub Releases (recommended)

1. Open **[Releases](https://github.com/evertonfxavier/map-storage/releases)** and download the latest `map-storage-vX.Y.Z.zip`.
2. Copy the ZIP to your Steam Deck (USB, SSH, cloud, etc.).
3. In **Game Mode**: Quick Access (⋯) → **Decky** → **Settings** (gear).
4. Enable **Developer Mode**.
5. Tap **Install Plugin from ZIP** and select the file.
6. Open **Map Storage** from the Decky plugin list.

### Update

Install the newer ZIP over the existing plugin (same steps as install). No need to uninstall first unless Decky shows a stuck install state.

## Usage

| Action | What it does |
|--------|----------------|
| **Rescan all storage** | Lists connected disks/partitions (excludes loop/ram/system) |
| **Filesystem label** | ext4 label used for mount + Steam library (max 16 chars) |
| **Format before setup** | Wipes and creates partition/filesystem before automount |
| **Configure automount (no format)** | Keeps existing data; sets udev + systemd + udisks mount |
| **Format only** | Destructive format without full service setup |
| **Check status** | Partition, mount point, service state |

After setup, reboot to Game Mode and check **Settings → Storage** for your library label.

### Without formatting

The plugin does **not** erase data. It:

1. Finds the partition (by label or selected path)
2. Installs automount (udev + `map-storage-automount.service`)
3. Mounts via `udisksctl` as user `deck`
4. Ensures Steam folder structure if missing

You need an existing compatible filesystem (or use **format** first).

## Development

### Requirements

- Node.js 20+
- pnpm 9+

```bash
pnpm install
pnpm run build        # frontend only → dist/
pnpm run build:zip    # local ZIP in out/ (uses Decky CLI if Docker is running)
```

CI uses `scripts/ci-build-zip.sh` (same steps as GitHub Actions).

### Deploy to Deck (SSH)

Copy `.vscode/defsettings.json` to `.vscode/settings.json`, set your Deck IP/password, then use VS Code task **builddeploy** or:

```bash
pnpm run build:zip
# Install the ZIP on-device via Decky UI
```

## Releases

Publishing is automated:

1. Bump `version` in `package.json` (optional — release workflow also sets it from the tag).
2. Commit and push.
3. Create and push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The [Release workflow](.github/workflows/release.yml) builds the plugin ZIP and attaches:

- `map-storage-v0.1.0.zip` — download this for installation
- `Map Storage.zip` — Decky CLI output name (same contents)

Manual release: **Actions → Release → Run workflow** with a version like `v0.1.0`.

## Project layout

| Path | Purpose |
|------|---------|
| `src/` | React UI (`@decky/ui`) |
| `main.py` | Python backend (`callable` APIs) |
| `plugin.json` | Decky plugin metadata |
| `scripts/` | ZIP build scripts |
| `.github/workflows/` | CI + release automation |
| `docs/` | Architecture/planning notes (optional reading) |

## Logs / debug

On the Deck:

```bash
sudo journalctl -u map-storage-automount.service -b
sudo systemctl status map-storage-automount.service
```

## License

BSD-3-Clause — see [LICENSE](LICENSE).  
Based on [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template).

## Disclaimer

Unofficial tool, not affiliated with Valve or Steam Deck Homebrew. Use at your own risk, especially when formatting drives.

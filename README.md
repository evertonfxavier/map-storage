# Map Storage

[![Build plugin](https://github.com/evertonfxavier/map-storage/actions/workflows/build-plugin.yml/badge.svg)](https://github.com/evertonfxavier/map-storage/actions/workflows/build-plugin.yml)

Decky Loader plugin for **Steam Deck** that makes extra storage (NVMe, USB, SD card, SATA) show up for Steam libraries:

- lists the drives you can use and gives each one an **on/off switch**
- enabled drives are mounted **on every boot, before Steam starts** (via udisks2, like SteamOS does for SD cards)
- drives are identified by **filesystem UUID**, so it keeps working when `nvme0n1` / `nvme1n1` swap places between boots
- optional **format** (ext4 + custom label), with a confirmation dialog
- creates `steamapps` and `libraryfolder.vdf` when a drive has no Steam library yet

> **Warning:** formatting erases all data on the selected drive.

The disk that holds SteamOS is never offered (not for automount, not for format), and the backend enforces that on its own, whatever the UI sends.

## Prerequisites

- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) installed on your Steam Deck
- A drive with an `ext4`, `btrfs`, `xfs` or `f2fs` filesystem (or use **format**)
- This plugin requests the **`root` flag**: it writes a udev rule, a systemd unit and a helper script under `/etc`

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

Open **Map Storage** in the Quick Access menu.

| Control | What it does |
|---------|--------------|
| **Drive switch** (Your drives) | On: mount now and on every boot. Off: stop auto-mounting and unmount it if nothing is using it |
| **Re-scan drives** | Refresh the list |
| **Re-apply and mount now** (Advanced) | Rewrite the udev rule / boot unit and mount enabled drives again |
| **Show mount logs** (Advanced) | Output of the mount helper for this boot |
| **Erase, format and enable…** (Advanced) | Pick a drive, set a label, confirm; creates a GPT + ext4 and enables it |

The status card at the top turns green when every enabled drive is mounted.

### Upgrading from 0.1.x

On first load the plugin converts the old setup (a device path + label) to a UUID. It never trusts the old `/dev/...` path, because that path may now point to another disk. It adopts the drive with the old label, or the single drive that looks like your Steam library (`NVMe1TB` or mounted under `/run/media`). If it cannot decide, nothing is enabled — just flip the switch.

## How it works

1. **UUID, not `/dev/nvmeXnY`.** With two NVMe drives the kernel can number them differently on each boot. Everything (config, udev rule, mount helper) is keyed by filesystem UUID.
2. **Root + udisks `as-user`.** `/etc/map-storage/map-storage-mount.sh` calls udisks over D-Bus as root with `as-user=deck`, the same call SteamOS uses for SD cards. A plain `udisksctl mount` as `deck` is refused by polkit for non-removable NVMe drives.
3. **Mounted before Steam.** `map-storage-automount.service` runs `Before=sddm.service`; a udev rule handles hot-plug. If Steam starts before the library exists, it cannot see it.
4. **Self-heal.** SteamOS updates or a plugin reinstall can drop `/etc` changes; on every load the plugin re-creates what is missing from its saved config (`homebrew/settings/Map Storage/config.json`).

The plugin does not touch `steamos-readonly`.

## Troubleshooting

```bash
journalctl -b -t map-storage-mount.sh          # what the helper did this boot
systemctl status map-storage-automount.service
cat /etc/udev/rules.d/99-map-storage-automount.rules
```

To remove everything by hand: `sudo systemctl disable map-storage-automount.service && sudo rm -rf /etc/map-storage /etc/udev/rules.d/99-map-storage-automount.rules /etc/systemd/system/map-storage-automount.service`.

## Development

### Requirements

- Node.js 20+
- pnpm 9+

```bash
pnpm install
pnpm run build        # frontend only → dist/
pnpm run build:zip    # local ZIP in out/ (uses Decky CLI if Docker is running)
pnpm test             # backend unit tests (python3, no dependencies)
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
| `tests/` | Backend unit tests + a real `lsblk` fixture from a Deck |
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

#!/usr/bin/env bash
# Installs Decky CLI into ./cli/decky (same approach as template setup + unifideck).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_BIN="${ROOT_DIR}/cli/decky"
CLI_RELEASE_BASE="https://github.com/SteamDeckHomebrew/cli/releases/latest/download"

if [[ -x "${CLI_BIN}" ]]; then
  echo "Decky CLI already installed: ${CLI_BIN}"
  exit 0
fi

OS="$(uname -s)"
ARCH="$(uname -m)"
ASSET=""

case "${OS}" in
  Linux)
    case "${ARCH}" in
      x86_64)  ASSET="decky-linux-x86_64" ;;
      arm64|aarch64) ASSET="decky-linux-aarch64" ;;
      *) echo "Unsupported Linux arch: ${ARCH}" >&2; exit 1 ;;
    esac
    ;;
  Darwin)
    case "${ARCH}" in
      x86_64)  ASSET="decky-macOS-x86_64" ;;
      arm64)   ASSET="decky-macOS-aarch64" ;;
      *) echo "Unsupported macOS arch: ${ARCH}" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: ${OS}" >&2
    exit 1
    ;;
esac

mkdir -p "${ROOT_DIR}/cli"
URL="${CLI_RELEASE_BASE}/${ASSET}"

echo "Downloading Decky CLI (${ASSET})..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL -o "${CLI_BIN}" "${URL}"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "${CLI_BIN}" "${URL}"
else
  echo "Need curl or wget to download Decky CLI." >&2
  exit 1
fi

chmod +x "${CLI_BIN}"
echo "Installed: ${CLI_BIN}"

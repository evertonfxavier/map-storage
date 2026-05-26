#!/usr/bin/env bash
# CI/local build: frontend + Decky plugin ZIP in out/
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DECKY_CLI_VERSION="${DECKY_CLI_VERSION:-0.0.8}"
OUT_DIR="${ROOT_DIR}/out"
CLI_BIN="${ROOT_DIR}/cli/decky"

read_plugin_name() {
  node -e "const p=require('./plugin.json'); process.stdout.write(p.name||'plugin')"
}

read_package_version() {
  node -e "const p=require('./package.json'); process.stdout.write(p.version||'0.0.0')"
}

echo "==> map-storage CI build"
echo "    version: $(read_package_version)"

echo "==> pnpm install"
export CI=true
pnpm install --frozen-lockfile

echo "==> pnpm build"
pnpm run build

mkdir -p "${OUT_DIR}"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "==> Decky CLI (docker available)"
  mkdir -p "${ROOT_DIR}/cli"
  curl -fsSL \
    -o "${CLI_BIN}" \
    "https://github.com/SteamDeckHomebrew/cli/releases/download/${DECKY_CLI_VERSION}/decky-linux-x86_64"
  chmod +x "${CLI_BIN}"
  "${CLI_BIN}" plugin build "${ROOT_DIR}"
else
  echo "==> Manual ZIP packager (no docker)"
  bash "${ROOT_DIR}/scripts/package-zip-manual.sh"
fi

PLUGIN_NAME="$(read_plugin_name)"
VERSION="$(read_package_version)"
SOURCE_ZIP="${OUT_DIR}/${PLUGIN_NAME}.zip"
RELEASE_ZIP="${OUT_DIR}/map-storage-v${VERSION}.zip"

if [[ ! -f "${SOURCE_ZIP}" ]]; then
  echo "Expected zip not found: ${SOURCE_ZIP}" >&2
  ls -la "${OUT_DIR}" >&2 || true
  exit 1
fi

cp -f "${SOURCE_ZIP}" "${RELEASE_ZIP}"
echo "==> Release asset: ${RELEASE_ZIP}"
ls -lh "${OUT_DIR}"/*.zip

#!/usr/bin/env bash
# Local build: out/Map Storage.zip + out/map-storage-vX.Y.Z.zip
# Usage: pnpm run build:zip
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ "${CI:-}" == "true" ]] || { [[ "$(uname -s)" == "Linux" ]] && command -v docker >/dev/null && docker info >/dev/null 2>&1; }; then
  exec bash "${ROOT_DIR}/scripts/ci-build-zip.sh"
fi

CLI_BIN="${ROOT_DIR}/cli/decky"
OUT_DIR="${ROOT_DIR}/out"

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

echo "==> map-storage: local build"

if [[ ! -x "${CLI_BIN}" ]]; then
  bash "${ROOT_DIR}/scripts/install-decky-cli.sh"
fi

pnpm run build

for f in plugin.json package.json main.py LICENSE; do
  [[ -f "${ROOT_DIR}/${f}" ]] || { echo "Missing ${f}" >&2; exit 1; }
done

mkdir -p "${OUT_DIR}"
PACKAGED=0

if docker_available; then
  echo "==> Decky CLI"
  "${CLI_BIN}" plugin build "${ROOT_DIR}" && PACKAGED=1
else
  echo "==> Manual ZIP (Docker not running)"
fi

if [[ "${PACKAGED}" -eq 0 ]]; then
  bash "${ROOT_DIR}/scripts/package-zip-manual.sh"
fi

VERSION=$(node -e "console.log(require('./package.json').version)")
PLUGIN_NAME=$(node -e "console.log(require('./plugin.json').name)")
cp -f "${OUT_DIR}/${PLUGIN_NAME}.zip" "${OUT_DIR}/map-storage-v${VERSION}.zip"

echo ""
ls -lh "${OUT_DIR}"/*.zip
echo "Install on Deck: Decky → Settings → Install Plugin from ZIP"

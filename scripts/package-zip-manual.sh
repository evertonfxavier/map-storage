#!/usr/bin/env bash
# Creates a Decky-installable ZIP without Docker (layout from decky-plugin-template).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/out"

read_plugin_name() {
  if command -v node >/dev/null 2>&1; then
    node -e "const p=require('${ROOT_DIR}/plugin.json'); process.stdout.write(p.name||'plugin')"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import json; print(json.load(open('${ROOT_DIR}/plugin.json'))['name'])"
    return
  fi
  echo "plugin"
}

PLUGIN_NAME="$(read_plugin_name)"
ZIP_PATH="${OUT_DIR}/${PLUGIN_NAME}.zip"
STAGING="$(mktemp -d)"
PLUGIN_DIR="${STAGING}/${PLUGIN_NAME}"

cleanup() { rm -rf "${STAGING}"; }
trap cleanup EXIT

mkdir -p "${PLUGIN_DIR}/dist" "${OUT_DIR}"

for f in plugin.json package.json main.py LICENSE; do
  cp "${ROOT_DIR}/${f}" "${PLUGIN_DIR}/"
done
cp "${ROOT_DIR}/dist/index.js" "${PLUGIN_DIR}/dist/"

if [[ -d "${ROOT_DIR}/defaults" ]]; then
  cp -a "${ROOT_DIR}/defaults" "${PLUGIN_DIR}/"
fi

if [[ -d "${ROOT_DIR}/bin" ]]; then
  cp -a "${ROOT_DIR}/bin" "${PLUGIN_DIR}/"
fi

if [[ -f "${ROOT_DIR}/README.md" ]]; then
  cp "${ROOT_DIR}/README.md" "${PLUGIN_DIR}/"
fi

rm -f "${ZIP_PATH}"
(
  cd "${STAGING}"
  if command -v zip >/dev/null 2>&1; then
    zip -rq "${ZIP_PATH}" "${PLUGIN_NAME}"
  else
    echo "zip command not found." >&2
    exit 1
  fi
)

echo "    Manual package: ${ZIP_PATH}"

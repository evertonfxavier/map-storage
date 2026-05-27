#!/bin/bash
# Run on Steam Deck with: sudo bash deck-repair-nvme1tb.sh
set -euo pipefail

LABEL="NVMe1TB"
MOUNT_SCRIPT="/usr/local/bin/mount-nvme1tb.sh"
SERVICE="/etc/systemd/system/mount-nvme1tb.service"

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

steamos-readonly disable 2>/dev/null || true

mkdir -p /usr/local/bin

cat > "$MOUNT_SCRIPT" << 'EOF'
#!/bin/bash
set -e
LABEL="NVMe1TB"
MAX_RETRIES=10
RETRY_DELAY=2
DECK_USER="deck"

for i in $(seq 1 $MAX_RETRIES); do
    PARTITION=$(/usr/bin/blkid -L "$LABEL" 2>/dev/null || echo "")
    if [[ -z "$PARTITION" ]]; then
        sleep $RETRY_DELAY
        continue
    fi
    if /usr/bin/findmnt -no TARGET "$PARTITION" >/dev/null 2>&1; then
        MOUNT_AT=$(/usr/bin/findmnt -no TARGET "$PARTITION")
        chown 1000:1000 "$MOUNT_AT" 2>/dev/null || true
        exit 0
    fi
    if runuser -u "$DECK_USER" -- /usr/bin/udisksctl mount -b "$PARTITION" --no-user-interaction; then
        sleep 1
        exit 0
    fi
    sleep $RETRY_DELAY
done

PARTITION=$(/usr/bin/blkid -L "$LABEL" 2>/dev/null || echo "")
if [[ -n "$PARTITION" ]]; then
    MOUNT_POINT="/run/media/$DECK_USER/$LABEL"
    mkdir -p "$MOUNT_POINT"
    /usr/bin/mount -o rw,noatime "$PARTITION" "$MOUNT_POINT"
    chown 1000:1000 "$MOUNT_POINT"
    exit 0
fi
exit 1
EOF

chmod 755 "$MOUNT_SCRIPT"

cat > "$SERVICE" << 'EOF'
[Unit]
Description=Mount NVMe1TB Steam Library via udisks2
After=udisks2.service multi-user.target
Wants=udisks2.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart=/usr/local/bin/mount-nvme1tb.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mount-nvme1tb.service
systemctl restart mount-nvme1tb.service

echo "=== service ==="
systemctl status mount-nvme1tb.service --no-pager | head -15 || true

echo "=== mount ==="
findmnt /dev/nvme0n1p1 2>/dev/null || true
ls -la /run/media/deck/ 2>/dev/null || true
df -h /run/media/deck/NVMe1TB 2>/dev/null || true

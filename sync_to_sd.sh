#!/bin/zsh
#
# sync_to_sd.sh - Copy already-converted photos from the staging folder
# straight onto the Inky Frame's microSD card, no conversion step.
#
# Usage:
#   ./sync_to_sd.sh          copy only new files
#   ./sync_to_sd.sh --all    re-copy everything (overwrite existing)
#
# The SD card mount point is auto-detected by looking for a /Volumes/*
# directory with a "photos" folder. Override with SD_MOUNT=/Volumes/Name.

set -euo pipefail

STAGING_DIR="${STAGING_DIR:-$HOME/Pictures/inky_photos}"
RSYNC_FLAGS=(-av --ignore-existing)

if [[ "${1:-}" == "--all" ]]; then
  RSYNC_FLAGS=(-av)
fi

if [[ -z "${SD_MOUNT:-}" ]]; then
  SD_MOUNT=""
  for vol in /Volumes/*(N); do
    if [[ -d "$vol/photos" ]]; then
      SD_MOUNT="$vol"
      break
    fi
  done
fi

if [[ -z "$SD_MOUNT" ]]; then
  echo "No SD card with a /photos folder found under /Volumes." >&2
  echo "Insert the microSD card, or set SD_MOUNT=/Volumes/YourCardName and re-run." >&2
  exit 1
fi

echo "==> Syncing $STAGING_DIR -> $SD_MOUNT/photos"
rsync "${RSYNC_FLAGS[@]}" "$STAGING_DIR"/*.jpg "$SD_MOUNT/photos/"

if command -v dot_clean >/dev/null 2>&1; then
  dot_clean -m "$SD_MOUNT/photos"
fi

echo "==> Done. Eject the card with: diskutil eject \"$SD_MOUNT\""

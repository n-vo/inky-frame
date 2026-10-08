#!/bin/zsh
#
# publish_photos.sh - Convert new iPhone photos and push them onto the
# Inky Frame's microSD card.
#
# Pipeline:
#   1. ~/Pictures/InkySource   <- drop raw iPhone photos here (HEIC/JPG, any size)
#   2. ~/Pictures/inky_photos <- converted 800x480 baseline JPGs (staging area)
#   3. SD card /photos        <- synced from the staging area
#
# Usage:
#   ./publish_photos.sh            convert new photos + sync to SD card
#   ./publish_photos.sh --convert-only   only do step 1-2, skip the SD card
#   ./publish_photos.sh --force    re-convert everything, even if already done
#
# The SD card mount point is auto-detected by looking for a /Volumes/*
# directory that already has a "photos" folder. Override by exporting
# SD_MOUNT=/Volumes/WhateverItsCalled before running.

set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$HOME/Pictures/InkySource}"
STAGING_DIR="${STAGING_DIR:-$HOME/Pictures/inky_photos}"
FORCE=0
CONVERT_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --convert-only) CONVERT_ONLY=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! command -v magick >/dev/null 2>&1; then
  echo "ImageMagick not found. Install it with: brew install imagemagick" >&2
  exit 1
fi

mkdir -p "$STAGING_DIR"

echo "==> Converting new photos from $SOURCE_DIR"
converted=0
skipped=0

for f in "$SOURCE_DIR"/*.{jpg,jpeg,JPG,JPEG,heic,HEIC,png,PNG}(N); do
  name=$(basename "${f%.*}")
  out="$STAGING_DIR/$name.jpg"

  if [[ -f "$out" && $FORCE -eq 0 ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  magick "$f" -auto-orient -resize 800x480^ -gravity center -extent 800x480 \
    -interlace none -quality 85 "$out"
  echo "  converted: $name.jpg"
  converted=$((converted + 1))
done

echo "==> Done: $converted converted, $skipped already up to date"

if [[ $CONVERT_ONLY -eq 1 ]]; then
  exit 0
fi

# Auto-detect the SD card mount point if not set explicitly.
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
  echo ""
  echo "No SD card with a /photos folder found under /Volumes." >&2
  echo "Insert the microSD card (with a 'photos' folder already on it)," >&2
  echo "or set SD_MOUNT=/Volumes/YourCardName and re-run." >&2
  echo "(Ran with --convert-only skipped; converted files are staged in $STAGING_DIR)" >&2
  exit 1
fi

echo "==> Syncing to SD card at $SD_MOUNT/photos"
rsync -av --ignore-existing "$STAGING_DIR"/*.jpg "$SD_MOUNT/photos/"

# Belt-and-suspenders: strip any AppleDouble metadata files macOS may have
# left behind on the FAT32 card (main.py also filters these, but keep the
# card itself clean too).
if command -v dot_clean >/dev/null 2>&1; then
  dot_clean -m "$SD_MOUNT/photos"
fi

echo "==> Done. Eject the card with: diskutil eject \"$SD_MOUNT\""

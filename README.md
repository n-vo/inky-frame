# inky-frame

A battery-friendly photo frame for the [Pimoroni Inky Frame 7.3"](https://shop.pimoroni.com/products/inky-frame-7-3) (Raspberry Pi Pico W, 800×480, 7-color e-paper), plus macOS scripts that get iPhone photos onto its microSD card.

Each time the frame wakes, it shows one random photo from the SD card and deep-sleeps again. E-paper holds the image with zero power, so the board is off almost all the time and runs for a long time on batteries.

| File | What it does |
| --- | --- |
| `main.py` | The slideshow app that runs on the Inky Frame |
| `publish_photos.sh` | Converts photos to frame-ready JPGs and syncs them to the SD card |
| `sync_to_sd.sh` | Syncs photos you've already converted to the SD card, without converting again |

## Hardware & firmware

- Pimoroni Inky Frame 7.3" (Pico W)
- Pimoroni Inky Frame MicroPython firmware (tested with `pimoroni-inky_frame-v1.22.2-micropython.uf2`), which provides `picographics`, `jpegdec`, `inky_frame` and `sdcard`
- A microSD card (FAT32)
- Battery pack, or USB power

To flash the firmware, hold **BOOTSEL** on the Pico W while plugging it in, then drag the `.uf2` onto the `RPI-RP2` drive.

## Installing

Copy `main.py` to the board with [Thonny](https://thonny.org/) or [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html), then reset the board:

```sh
mpremote cp main.py :main.py
```

No WiFi or secrets are needed.

## Usage

- **Button A / B** – show a new random photo now
- **Timer** – a new random photo every 24 h (`SLIDESHOW_INTERVAL` in `main.py`)

## Photo requirements

Photos **must** be:

- JPEG, **baseline** (not progressive, which `jpegdec` can't decode)
- **800×480** pixels
- In a folder called `photos` at the root of the SD card

Files starting with `.` (including macOS `._*` AppleDouble files) are skipped. The scripts below take care of the format and size for you.

## Getting photos onto the card (macOS)

You need [ImageMagick](https://imagemagick.org/) (`brew install imagemagick`).

1. Put the original photos (HEIC, JPG or PNG, any size) in `~/Pictures/InkySource`.
2. Insert the SD card. It needs a `photos` folder at its root already, because that's how the scripts find the card.
3. Run:

```sh
./publish_photos.sh                 # convert new photos + copy them to the SD card
./publish_photos.sh --convert-only  # convert only, don't touch the SD card
./publish_photos.sh --force         # convert everything again
```

Each photo is auto-rotated, center-cropped to fill 800×480, and saved as a baseline JPEG (quality 85) in `~/Pictures/inky_photos`. New files are then rsynced to the card and `dot_clean` removes macOS metadata files.

To copy staged photos without converting again:

```sh
./sync_to_sd.sh        # copy only new files
./sync_to_sd.sh --all  # copy everything and overwrite
```

Environment overrides for both scripts:

| Variable | Default |
| --- | --- |
| `SOURCE_DIR` | `~/Pictures/InkySource` (`publish_photos.sh` only) |
| `STAGING_DIR` | `~/Pictures/inky_photos` |
| `SD_MOUNT` | Auto-detected: the first `/Volumes/*` that contains a `photos` folder |

When it's done, eject the card with `diskutil eject /Volumes/<card>`.

## How it works

- **Low memory use.** The directory is streamed with `os.ilistdir()` and a photo is picked by reservoir sampling, so memory use stays the same however many photos are on the card. (`os.listdir()` runs out of heap with a few hundred files, because the 800×480 framebuffer already takes most of the RP2040's RAM.)
- **No back-to-back repeats.** A 16-bit hash of the last filename is saved in RTC memory, which survives power-off. If the next pick matches it, a second pick is shown instead.
- **Random seed without WiFi.** `random` isn't seeded automatically on rp2 and the clock is never synced, so the seed combines `ticks_us()` jitter with the chip's unique ID.
- **Error screens.** If the card can't be mounted, has no photos, or a file won't decode, the frame shows `NO SD CARD`, `NO PHOTOS` or `BAD IMAGE` instead of failing silently.
- **Power.** GPIO 2 is the Inky Frame's power latch. `main.py` sets it high on its very first lines so the board stays on, and sets it low to power off. On battery, setting it low cuts power completely until the RTC alarm or a button press wakes the board. On USB power the latch has no effect, so the app falls back to `machine.lightsleep()`. The onboard LED is lit while the app is working.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `NO SD CARD` | Check that the card is seated and formatted FAT32. |
| `NO PHOTOS` | Make sure the JPGs are in `/photos` at the card's root, not in a subfolder. |
| `BAD IMAGE` | The file is probably a progressive JPEG or the wrong size. Run it through `publish_photos.sh --force`. |
| Same photo every time | Make sure `photos` contains more than one JPG. |

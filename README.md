# inky-frame

MicroPython apps for the [Pimoroni Inky Frame 7.3"](https://shop.pimoroni.com/products/inky-frame-7-3) (Raspberry Pi Pico W, 800×480, 7-color e-paper), plus macOS helper scripts for getting photos onto its microSD card.

Each app follows the same battery-friendly pattern: **wake → do one job → draw → deep sleep**. E-paper holds the image with zero power, so the board is powered off almost all the time and runs for a long time on batteries.

| File | What it does |
| --- | --- |
| `photos.py` | **Photo slideshow.** Shows a random photo from the SD card once a day or on button press. |
| `weather.py` | **Dashboard.** 7-day weather forecast (button A) and home-cluster status (button B). |
| `main.py` | The app that actually runs on boot. Copy whichever app you want over it. |
| `publish_photos.sh` | Converts iPhone photos to frame-ready JPGs and syncs them to the SD card. |
| `sync_to_sd.sh` | Syncs photos you've already converted to the SD card, without converting again. |

## Hardware & firmware

- Pimoroni Inky Frame 7.3" (Pico W)
- Pimoroni Inky Frame MicroPython firmware (tested with `pimoroni-inky_frame-v1.22.2-micropython.uf2`), which provides `picographics`, `jpegdec`, `inky_frame` and `sdcard`
- A microSD card (FAT32) for the photo slideshow
- Battery pack, or USB power

To flash the firmware, hold **BOOTSEL** on the Pico W while plugging it in, then drag the `.uf2` onto the `RPI-RP2` drive.

## Installing an app

The Inky Frame runs `main.py` on boot. Copy the app you want to the board as `main.py`, using [Thonny](https://thonny.org/) or [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html):

```sh
# Photo slideshow
mpremote cp photos.py :main.py

# Weather / cluster dashboard (also needs secrets.py, see below)
mpremote cp weather.py :main.py
mpremote cp secrets.py :secrets.py
```

Then reset the board.

---

## Photo slideshow (`photos.py`)

Picks a random JPG from `/photos` on the microSD card, shows it, and deep-sleeps for 24 hours.

- **Button A / B** – show a new random photo now
- **Timer** – a new random photo every 24 h (`SLIDESHOW_INTERVAL`)

How it works:

- **Low memory use.** The directory is streamed with `os.ilistdir()` and a photo is picked by reservoir sampling, so memory use stays the same however many photos are on the card. (`os.listdir()` runs out of heap with a few hundred files.)
- **No back-to-back repeats.** A 16-bit hash of the last filename is saved in RTC memory. If the next pick matches it, a second pick is shown instead.
- **Random seed without WiFi.** `random` isn't seeded automatically on rp2 and the clock is never synced, so the seed combines `ticks_us()` jitter with the chip's unique ID.
- **Error screens.** If the card can't be mounted, has no photos, or a file won't decode, the frame shows `NO SD CARD`, `NO PHOTOS` or `BAD IMAGE` instead of failing silently.

### Photo requirements

Photos **must** be:

- JPEG, **baseline** (not progressive, which `jpegdec` can't decode)
- **800×480** pixels
- In a folder called `photos` at the root of the SD card

Files starting with `.` (including macOS `._*` AppleDouble files) are skipped.

### Getting photos onto the card (macOS)

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

---

## Weather & cluster dashboard (`weather.py`)

Two screens that share a black header bar showing the location, date and time:

- **Button A – Weather Station.** Current temperature, conditions and wind; today's high/low and chance of rain; a 7-day forecast strip; UV index, sunrise and sunset. Data comes from [Open-Meteo](https://open-meteo.com/), which needs no API key. Refreshes every 30 minutes.
- **Button B – Cluster Status.** One card per node (up to two) with CPU % and a bar, temperature and 1-minute load. Values over the limits (CPU > 50 %, temp > 55 °C) turn red. Refreshes every 5 minutes.

The current screen is saved in RTC memory, so a timer wake refreshes whichever screen was showing last. WiFi is on only while data is being fetched, and the clock is set over NTP on first boot.

### `secrets.py`

Create a `secrets.py` next to `main.py` on the board (it's gitignored):

```python
WIFI_SSID = "your-network"
WIFI_PASSWORD = "your-password"
STATUS_API_URL = "http://your-server:port/status"
```

### Status API format

`STATUS_API_URL` must return JSON like this:

```json
{
  "nodes": [
    { "name": "node-1", "cpu_pct": 12.5, "temp_c": 48.0, "load1": 0.42 },
    { "name": "node-2", "cpu_pct": 63.0, "temp_c": 57.2, "load1": 1.87 }
  ]
}
```

### Configuration

At the top of `weather.py`:

- `LATITUDE`, `LONGITUDE`, `LOCATION_NAME`: forecast location (defaults to Sugar Land, TX)
- `WEATHER_REFRESH`, `SERVER_REFRESH`: auto-refresh intervals in seconds

> Note: the local time shown and the Open-Meteo `timezone` setting are hard-coded to US Central Time (`_dst_offset_seconds()` and `fetch_weather()`). Change both if you live in another time zone.

---

## Power notes

- GPIO 2 is the Inky Frame's power latch. Both apps set it high on their very first lines so the board stays on, and set it low to power off. On battery, setting it low cuts power completely until the RTC alarm or a button press wakes the board.
- On USB power the latch has no effect, so the apps fall back to `machine.lightsleep()`.
- The onboard LED is lit while the app is working and turns off before sleep.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `NO SD CARD` | Check that the card is seated and formatted FAT32. |
| `NO PHOTOS` | Make sure the JPGs are in `/photos` at the card's root, not in a subfolder. |
| `BAD IMAGE` | The file is probably a progressive JPEG or the wrong size. Run it through `publish_photos.sh --force`. |
| Same photo every time | Make sure all photos are on the card and `photos` contains more than one JPG. |
| Weather/cluster `ERROR` | Check WiFi details in `secrets.py`, and that `STATUS_API_URL` can be reached from the frame's network. |

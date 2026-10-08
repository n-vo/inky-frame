"""
Photo Slideshow - Pimoroni Inky Frame 7.3" (Pico W)

Shows one random photo per wake cycle from a microSD card, then deep-sleeps.
E-paper keeps the image on screen with zero power, so battery life is great.

Buttons:
  A -> new random photo
  B -> new random photo
  (timer wake also picks a new random photo automatically)

Photo prep (IMPORTANT):
  * Format: JPG, BASELINE (not progressive), resized to 800x480.
  * Copy them into a folder called /photos on the microSD card.
  * Progressive JPEGs will NOT decode -- re-save as baseline if unsure.
"""

# Power latch - MUST be first
import machine

_pwr = machine.Pin(2, machine.Pin.OUT)
_pwr.value(1)

_led = machine.Pin("LED", machine.Pin.OUT)
_led.on()

import gc
import os
import random
import time
from machine import Pin, SPI
import sdcard
import uos
import jpegdec
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
import inky_frame

# Hardware
graphics = PicoGraphics(display=DISPLAY)
WIDTH, HEIGHT = graphics.get_bounds()

# Colors (used only for the "no photos" fallback screen)
PEN_WHITE = 1
PEN_BLACK = 0
PEN_RED = 4

# Config
PHOTO_DIR = "/sd/photos"       # folder on the SD card holding the JPGs
SLIDESHOW_INTERVAL = 86400     # seconds between auto-advances (24 hours)

# Persistent state across deep sleeps lives in RTC memory (survives power-off).
# Layout: [magic=0xAB, index_low, index_high]
rtc = machine.RTC()


def mount_sd():
    """Mount the microSD card at /sd. Returns True on success."""
    try:
        sd_spi = SPI(
            0,
            sck=Pin(18, Pin.OUT),
            mosi=Pin(19, Pin.OUT),
            miso=Pin(16, Pin.OUT),
        )
        sd = sdcard.SDCard(sd_spi, Pin(22))
        uos.mount(sd, "/sd")
        print("SD card mounted")
        return True
    except Exception as e:
        print("SD mount failed: {}".format(e))
        return False


def _is_photo_name(name):
    if name.startswith("._") or name.startswith("."):
        return False  # skip macOS AppleDouble metadata files and hidden files
    lower = name.lower()
    return lower.endswith(".jpg") or lower.endswith(".jpeg")


def _name_hash(name):
    """Cheap 16-bit hash so RTC memory only needs 2 bytes to remember
    the previously-shown filename (not the whole string)."""
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFF
    return h


def pick_random_photo(avoid_hash):
    """Reservoir-sample a random photo filename from PHOTO_DIR.

    Deliberately avoids os.listdir(), which builds the full directory
    listing in memory at once -- with hundreds of photos on the card that
    exhausts the RP2040's free heap (most of it already used by the 800x480
    framebuffer) and raises MemoryError. os.ilistdir() streams entries one
    at a time instead, so memory use stays constant no matter how many
    photos are on the card.
    """
    try:
        entries = os.ilistdir(PHOTO_DIR)
    except Exception as e:
        print("Cannot read {}: {}".format(PHOTO_DIR, e))
        return None, 0

    count = 0
    reservoir = [None, None]  # 2 candidates, so we can dodge an immediate repeat
    for entry in entries:
        name = entry[0]
        if not _is_photo_name(name):
            continue
        count += 1
        if count <= 2:
            reservoir[count - 1] = name
        else:
            j = random.randrange(count)
            if j < 2:
                reservoir[j] = name

    print("Found {} photo(s)".format(count))
    if count == 0:
        return None, 0

    chosen = reservoir[0]
    if reservoir[1] is not None and _name_hash(chosen) == avoid_hash:
        chosen = reservoir[1]

    return "{}/{}".format(PHOTO_DIR, chosen), _name_hash(chosen)


def _rtc_read_hash():
    """Read the previously-shown photo's name hash from RTC memory."""
    try:
        mem = rtc.memory()
        if len(mem) >= 3 and mem[0] == 0xAB:
            return mem[1] | (mem[2] << 8)
    except Exception:
        pass
    return 0


def _rtc_write_hash(name_hash):
    """Persist the shown photo's name hash to RTC memory."""
    try:
        name_hash = name_hash & 0xFFFF
        rtc.memory(bytes([0xAB, name_hash & 0xFF, (name_hash >> 8) & 0xFF]))
    except Exception as e:
        print("RTC write failed: {}".format(e))


def draw_message(title, message):
    """Full-refresh fallback screen (no SD card / no photos)."""
    graphics.set_pen(PEN_WHITE)
    graphics.clear()
    graphics.set_pen(PEN_RED)
    graphics.text(title, 40, 180, scale=6)
    graphics.set_pen(PEN_BLACK)
    graphics.text(message, 40, 280, scale=2)
    graphics.update()


def show_photo(path):
    """Decode and display a single JPG, dithered to the 7-color palette."""
    print("Showing {}".format(path))
    gc.collect()  # jpegdec is memory-hungry; free up first
    try:
        j = jpegdec.JPEG(graphics)
        j.open_file(path)
        # Draw at (0,0), full scale. Image should already be 800x480.
        j.decode(0, 0, jpegdec.JPEG_SCALE_FULL, dither=True)
        graphics.update()
        return True
    except Exception as e:
        print("Decode failed: {}".format(e))
        draw_message("BAD IMAGE", "Could not decode {}".format(path))
        return False


def go_to_sleep(seconds):
    """Power off LED, then deep sleep. Buttons A/B wake via hardware."""
    print("Sleeping {}s ...".format(seconds))
    _led.off()

    # Schedule RTC wake (sleep_for takes minutes; keep at least 1)
    minutes = seconds // 60
    if minutes < 1:
        minutes = 1
    inky_frame.sleep_for(minutes)

    # Release power latch -- board powers off here if on battery.
    _pwr.value(0)

    # Fallback: if USB powered (latch ignored), use machine sleep.
    machine.lightsleep(seconds * 1000)


# ─── Main ─────────────────────────────────────────────────────────────────────
print("=== Photo Slideshow ===")

# Identify wake reason (both buttons just trigger an early random advance)
wake_a = inky_frame.button_a.read()
wake_b = inky_frame.button_b.read()
print("Wake: A={} B={}".format(wake_a, wake_b))

if not mount_sd():
    draw_message("NO SD CARD", "Insert a microSD card with a /photos folder.")
    go_to_sleep(SLIDESHOW_INTERVAL)

# `random` is NOT auto-seeded on rp2, and time.time() is never synced here
# (no WiFi/NTP), so both give the same value every boot. os.urandom() can
# block on this firmware's hardware RNG, so instead seed from ticks_us()
# (real-world jitter from the SD mount above varies it boot to boot) mixed
# with the chip's unique id. Both calls are guaranteed non-blocking.
try:
    _seed = time.ticks_us() ^ int.from_bytes(machine.unique_id(), "big")
    random.seed(_seed)
except Exception as e:
    print("Random seed failed: {}".format(e))

# Pick a random photo, avoiding an immediate repeat, without ever loading
# the full directory listing into memory (see pick_random_photo()).
prev_hash = _rtc_read_hash()
path, shown_hash = pick_random_photo(prev_hash)

if path is None:
    draw_message("NO PHOTOS", "Add baseline 800x480 JPGs to {}".format(PHOTO_DIR))
    go_to_sleep(SLIDESHOW_INTERVAL)

_led.off()
show_photo(path)

# Save position, then sleep until next advance
_rtc_write_hash(shown_hash)
go_to_sleep(SLIDESHOW_INTERVAL)

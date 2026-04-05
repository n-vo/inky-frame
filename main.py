import network
import urequests
import time
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
from secrets import WIFI_SSID, WIFI_PASSWORD, STATUS_API_URL

# Display setup
display = PicoGraphics(display=DISPLAY)
W, H = display.get_bounds()

# Colors
BLACK  = display.create_pen(0,   0,   0)
WHITE  = display.create_pen(255, 255, 255)
RED    = display.create_pen(255, 0,   0)
BLUE   = display.create_pen(0,   0,   255)
GREEN  = display.create_pen(0,   255, 0)
YELLOW = display.create_pen(255, 255, 0)
ORANGE = display.create_pen(255, 140, 0)

REFRESH_SECONDS = 300  # 5 minutes — e-ink friendly


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    return False


def fetch_status():
    try:
        r = urequests.get(STATUS_API_URL, timeout=10)
        data = r.json()
        r.close()
        return data
    except Exception:
        return None


def draw_node_card(x, y, w, h, node):
    cpu  = node["cpu_pct"]
    temp = node["temp_c"]
    load = node["load1"]
    name = node["name"]

    # Card background
    display.set_pen(WHITE)
    display.rectangle(x, y, w, h)

    # Card border
    display.set_pen(BLACK)
    display.rectangle(x, y, w, 4)

    # Node name
    display.set_pen(BLACK)
    display.set_font("bitmap8")
    display.set_thickness(2)
    display.text(name, x + 16, y + 20, scale=4)

    # CPU
    display.set_pen(BLACK)
    display.text("CPU", x + 16, y + 90, scale=3)
    cpu_color = RED if cpu > 80 else ORANGE if cpu > 50 else GREEN
    display.set_pen(cpu_color)
    display.text(f"{cpu:.1f}%", x + 120, y + 90, scale=3)

    # CPU bar
    bar_x = x + 16
    bar_y = y + 130
    bar_w = w - 32
    bar_h = 20
    display.set_pen(BLACK)
    display.rectangle(bar_x, bar_y, bar_w, bar_h)
    display.set_pen(cpu_color)
    display.rectangle(bar_x + 2, bar_y + 2, int((bar_w - 4) * cpu / 100), bar_h - 4)

    # Temperature
    display.set_pen(BLACK)
    display.text("TEMP", x + 16, y + 175, scale=3)
    temp_color = RED if temp > 70 else ORANGE if temp > 55 else GREEN
    display.set_pen(temp_color)
    display.text(f"{temp:.0f}C", x + 140, y + 175, scale=3)

    # Load
    display.set_pen(BLACK)
    display.text("LOAD", x + 16, y + 220, scale=3)
    display.set_pen(BLUE)
    display.text(f"{load:.2f}", x + 140, y + 220, scale=3)


def draw_error(message):
    display.set_pen(WHITE)
    display.clear()
    display.set_pen(RED)
    display.set_font("bitmap8")
    display.text("ERROR", 20, 20, scale=4)
    display.set_pen(BLACK)
    display.text(message, 20, 80, scale=2)
    display.update()


def draw_screen(data):
    display.set_pen(WHITE)
    display.clear()

    # Header
    display.set_pen(BLACK)
    display.rectangle(0, 0, W, 52)
    display.set_pen(WHITE)
    display.set_font("bitmap8")
    display.text("CLUSTER STATUS", 20, 12, scale=4)

    # Timestamp
    updated = data.get("updated", "")[:16].replace("T", "  ")
    display.set_pen(YELLOW)
    display.text(updated, W - 300, 18, scale=2)

    # Node cards side by side
    nodes = data.get("nodes", [])
    card_w = (W - 48) // 2
    card_h = H - 52 - 16
    card_y = 60

    for i, node in enumerate(nodes[:2]):
        card_x = 16 + i * (card_w + 16)
        draw_node_card(card_x, card_y, card_w, card_h, node)

    # Divider
    display.set_pen(BLACK)
    display.rectangle(W // 2 - 1, 60, 2, card_h)

    display.update()


# Main loop
while True:
    if not connect_wifi():
        draw_error("WiFi failed")
        time.sleep(60)
        continue

    data = fetch_status()
    if data is None:
        draw_error("API unreachable")
        time.sleep(60)
        continue

    draw_screen(data)
    time.sleep(REFRESH_SECONDS)

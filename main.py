"""
Unified Dashboard - Pimoroni Inky Frame 7.3" (Pico W)
Button A: Weather Station
Button B: Server Status
"""

# Power latch - MUST be first
import machine

_pwr = machine.Pin(2, machine.Pin.OUT)
_pwr.value(1)

_led = machine.Pin("LED", machine.Pin.OUT)
_led.on()

# All imports
import network
import urequests
import time
import ntptime
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY
import inky_frame
import secrets

# Hardware
graphics = PicoGraphics(display=DISPLAY)
WIDTH, HEIGHT = graphics.get_bounds()

# Colors
PEN_WHITE = 1
PEN_BLACK = 0
PEN_BLUE = 3
PEN_RED = 4
PEN_GREEN = 2
PEN_YELLOW = 5

# Config
LATITUDE = 29.6196
LONGITUDE = -95.6345
LOCATION_NAME = "Sugar Land, TX"
WEATHER_API = "https://api.open-meteo.com/v1/forecast"

UPDATE_INTERVAL = 1800  # 30 minutes

# State
current_display = "weather"
pressed_buttons = {"A": False, "B": False}


def ensure_wifi(retries=3):
    """Connect to WiFi"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return True

    for attempt in range(1, retries + 1):
        print("WiFi attempt {}/{}...".format(attempt, retries))
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout = timeout - 1
        if wlan.isconnected():
            print("WiFi connected: {}".format(wlan.ifconfig()[0]))
            return True
        wlan.disconnect()
        time.sleep(2)

    print("WiFi failed")
    return False


def sync_ntp():
    """Sync time via NTP"""
    try:
        ntptime.settime()
        print("NTP synced")
    except Exception as e:
        print("NTP failed: {}".format(e))


def _dst_offset_seconds(utc_tt):
    """Return UTC offset in seconds for US Central Time"""
    year = utc_tt[0]
    month = utc_tt[1]
    mday = utc_tt[2]
    hour = utc_tt[3]

    def nth_sunday(y, m, n):
        first_wd = time.localtime(int(time.mktime((y, m, 1, 0, 0, 0, 0, 0))))[6]
        days_to_sun = (6 - first_wd) % 7
        return 1 + days_to_sun + (n - 1) * 7

    dst_start = nth_sunday(year, 3, 2)
    dst_end = nth_sunday(year, 11, 1)

    in_dst = False
    if month > 3 and month < 11:
        in_dst = True
    elif month == 3 and (mday > dst_start or (mday == dst_start and hour >= 8)):
        in_dst = True
    elif month == 11 and not (mday > dst_end or (mday == dst_end and hour >= 7)):
        in_dst = True

    return -18000 if in_dst else -21600


def local_now():
    """Return (date_str, time_str, tz_label) in Central Time"""
    utc_tt = time.gmtime()
    offset = _dst_offset_seconds(utc_tt)
    local_t = time.time() + offset
    l = time.localtime(local_t)
    tz = "CDT" if offset == -18000 else "CST"
    date_str = "{:04d}-{:02d}-{:02d}".format(l[0], l[1], l[2])
    time_str = "{:02d}:{:02d}".format(l[3], l[4])
    return date_str, time_str, tz


def get_simple_weather():
    """Return simple hardcoded weather"""
    return {
        "temp": 75,
        "humidity": 65,
        "wind_speed": 8,
        "weather_code": 3,
        "is_day": 1,
    }


def weather_description(code, is_day):
    """Get weather description from WMO code"""
    if code == 0:
        return ("Clear sky", "SUN" if is_day else "MOON")
    elif code == 1 or code == 2:
        return ("Mostly clear", "PART")
    elif code == 3:
        return ("Overcast", "CLOUD")
    elif code == 45 or code == 48:
        return ("Foggy", "FOG")
    elif code in [51, 53, 55]:
        return ("Drizzle", "RAIN")
    elif code in [61, 63, 65]:
        return ("Rain", "RAIN")
    elif code in [71, 73, 75, 77, 80, 81, 82]:
        return ("Rain/Snow", "SNOW")
    elif code in [85, 86]:
        return ("Snow", "SNOW")
    elif code in [95, 96, 99]:
        return ("Thunderstorm", "STORM")
    else:
        return ("Unknown", "UNKNOWN")


def draw_weather(weather, date_str, time_str, tz):
    """Render weather dashboard"""
    graphics.set_pen(PEN_WHITE)
    graphics.clear()
    graphics.set_pen(PEN_BLACK)

    # Header
    graphics.text("WEATHER STATION", 40, 18, scale=3)
    graphics.text(
        "{} - {} {} {}".format(LOCATION_NAME, date_str, time_str, tz), 40, 52, scale=2
    )
    graphics.line(40, 74, WIDTH - 40, 74)

    if weather is None:
        graphics.set_pen(PEN_RED)
        graphics.text("ERROR", 200, 300, scale=6)
        graphics.set_pen(PEN_BLACK)
        graphics.text("Could not fetch weather", 80, 380, scale=2)
        graphics.line(40, 420, WIDTH - 40, 420)
        graphics.text("Press B for servers", 220, 440, scale=2)
        graphics.update()
        return

    # Weather data
    temp = weather.get("temp", 0)
    humidity = weather.get("humidity", 0)
    wind = weather.get("wind_speed", 0)
    code = weather.get("weather_code", 0)
    is_day = weather.get("is_day", 1)

    desc, icon = weather_description(code, is_day)

    # Main temperature
    graphics.set_pen(PEN_BLUE)
    graphics.text("{}F".format(int(temp)), 60, 120, scale=8)

    # Condition
    graphics.set_pen(PEN_BLACK)
    graphics.text(desc, 60, 250, scale=4)

    # Details box
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(60, 330, 680, 100)
    graphics.set_pen(PEN_WHITE)
    graphics.rectangle(62, 332, 676, 96)

    graphics.set_pen(PEN_BLACK)
    graphics.text("Humidity: {}%".format(int(humidity)), 75, 345, scale=2)
    graphics.text("Wind: {} mph".format(int(wind)), 75, 375, scale=2)

    graphics.line(40, 420, WIDTH - 40, 420)
    graphics.text("Press B for servers", 220, 440, scale=2)

    print("Display updated")
    graphics.update()


def fetch_server_status():
    """Fetch server status"""
    try:
        print("Fetching server status...")
        response = urequests.get(secrets.STATUS_API_URL, timeout=15)
        data = response.json()
        response.close()
        print("Server status fetched")
        return data
    except Exception as e:
        print("Server error: {}".format(e))
        return None


def draw_node_card(x, y, w, h, node):
    """Draw a node status card"""
    cpu = node.get("cpu_pct", 0)
    temp = node.get("temp_c", 0)
    load = node.get("load1", 0)
    name = node.get("name", "Unknown")

    # Card background
    graphics.set_pen(PEN_WHITE)
    graphics.rectangle(x, y, w, h)

    # Card border
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(x, y, w, 4)

    # Node name
    graphics.set_pen(PEN_BLACK)
    graphics.text(name, x + 16, y + 20, scale=4)

    # CPU
    graphics.set_pen(PEN_BLACK)
    graphics.text("CPU", x + 16, y + 90, scale=3)
    if cpu > 80:
        graphics.set_pen(PEN_RED)
    elif cpu > 50:
        graphics.set_pen(PEN_RED)
    else:
        graphics.set_pen(PEN_GREEN)
    graphics.text("{}%".format(int(cpu)), x + 120, y + 90, scale=3)

    # CPU bar
    bar_x = x + 16
    bar_y = y + 130
    bar_w = w - 32
    bar_h = 20
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(bar_x, bar_y, bar_w, bar_h)
    if cpu > 80:
        graphics.set_pen(PEN_RED)
    elif cpu > 50:
        graphics.set_pen(PEN_RED)
    else:
        graphics.set_pen(PEN_GREEN)
    bar_fill = int((bar_w - 4) * cpu / 100)
    if bar_fill > 0:
        graphics.rectangle(bar_x + 2, bar_y + 2, bar_fill, bar_h - 4)

    # Temperature
    graphics.set_pen(PEN_BLACK)
    graphics.text("TEMP", x + 16, y + 175, scale=3)
    if temp > 70:
        graphics.set_pen(PEN_RED)
    elif temp > 55:
        graphics.set_pen(PEN_RED)
    else:
        graphics.set_pen(PEN_GREEN)
    graphics.text("{}C".format(int(temp)), x + 140, y + 175, scale=3)

    # Load
    graphics.set_pen(PEN_BLACK)
    graphics.text("LOAD", x + 16, y + 220, scale=3)
    graphics.set_pen(PEN_BLUE)
    graphics.text(str(round(load, 2)), x + 140, y + 220, scale=3)


def draw_server_status(data):
    """Draw server status with node cards"""
    graphics.set_pen(PEN_WHITE)
    graphics.clear()

    if data is None:
        graphics.set_pen(PEN_RED)
        graphics.text("ERROR", 200, 300, scale=6)
        graphics.set_pen(PEN_BLACK)
        graphics.text("API unreachable", 100, 380, scale=2)
        graphics.line(40, 420, WIDTH - 40, 420)
        graphics.text("Press A for weather", 220, 440, scale=2)
        graphics.update()
        return

    # Header
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(0, 0, WIDTH, 52)
    graphics.set_pen(PEN_WHITE)
    graphics.text("CLUSTER STATUS", 20, 12, scale=4)

    # Timestamp
    updated = data.get("updated", "")[:16]
    graphics.set_pen(PEN_YELLOW)
    graphics.text(updated, WIDTH - 300, 18, scale=2)

    # Node cards side by side
    nodes = data.get("nodes", [])
    card_w = (WIDTH - 48) // 2
    card_h = HEIGHT - 52 - 16
    card_y = 60

    for i in range(min(2, len(nodes))):
        node = nodes[i]
        card_x = 16 + i * (card_w + 16)
        draw_node_card(card_x, card_y, card_w, card_h, node)

    # Divider
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(WIDTH // 2 - 1, 60, 2, card_h)

    graphics.set_pen(PEN_BLACK)
    graphics.text("Press A for weather", 220, HEIGHT - 20, scale=2)

    graphics.update()


print("=== Unified Dashboard ===")

if ensure_wifi():
    print("Syncing time...")
    sync_ntp()

    # Fetch initial data
    date_str, time_str, tz = local_now()
    weather_data = get_simple_weather()
    server_data = fetch_server_status()

    # Display weather first
    draw_weather(weather_data, date_str, time_str, tz)
    current_display = "weather"
    last_weather_update = time.time()
    last_server_update = time.time()

    print("Dashboard ready. Press buttons to switch displays.")

    while True:
        # Check button A
        if inky_frame.button_a.read():
            if not pressed_buttons["A"]:
                print("Button A - Weather")
                date_str, time_str, tz = local_now()
                weather_data = get_simple_weather()
                draw_weather(weather_data, date_str, time_str, tz)
                current_display = "weather"
                last_weather_update = time.time()
                pressed_buttons["A"] = True
        else:
            pressed_buttons["A"] = False

        # Check button B
        if inky_frame.button_b.read():
            if not pressed_buttons["B"]:
                print("Button B - Servers")
                server_data = fetch_server_status()
                draw_server_status(server_data)
                current_display = "server"
                last_server_update = time.time()
                pressed_buttons["B"] = True
        else:
            pressed_buttons["B"] = False

        # Refresh weather every 30 minutes if displayed
        if current_display == "weather":
            current_time = time.time()
            if current_time - last_weather_update >= UPDATE_INTERVAL:
                print("Refreshing weather...")
                date_str, time_str, tz = local_now()
                weather_data = get_simple_weather()
                draw_weather(weather_data, date_str, time_str, tz)
                last_weather_update = current_time

        # Refresh server data every 5 minutes if displayed
        if current_display == "server":
            current_time = time.time()
            if current_time - last_server_update >= 300:
                print("Refreshing server data...")
                server_data = fetch_server_status()
                draw_server_status(server_data)
                last_server_update = current_time

        time.sleep(0.1)
else:
    print("WiFi failed")

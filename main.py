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
    hour = l[3]
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    time_str = "{}:{:02d} {}".format(hour12, l[4], ampm)
    return date_str, time_str, tz


def fmt_time_12h(hhmm):
    """Convert 'HH:MM' 24h string to '12:34 AM' format"""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return "{}:{:02d} {}".format(h12, m, ampm)


def uv_label(uv):
    """Return UV risk label"""
    uv = int(uv)
    if uv <= 2:
        return "Low"
    elif uv <= 5:
        return "Moderate"
    elif uv <= 7:
        return "High"
    elif uv <= 10:
        return "Very High"
    else:
        return "Extreme"


def weather_description(code):
    """Get short condition label from WMO code"""
    if code == 0:
        return "Clear"
    elif code in [1, 2]:
        return "Pt Cloudy"
    elif code == 3:
        return "Overcast"
    elif code in [45, 48]:
        return "Foggy"
    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "Rain"
    elif code in [71, 73, 75, 77, 85, 86]:
        return "Snow"
    elif code in [95, 96, 99]:
        return "Tstorm"
    else:
        return "Unknown"


def day_abbrev(date_str):
    """Return 3-letter weekday from YYYY-MM-DD string"""
    y = int(date_str[:4])
    m = int(date_str[5:7])
    d = int(date_str[8:10])
    t = time.mktime((y, m, d, 0, 0, 0, 0, 0))
    wd = time.localtime(t)[6]  # 0=Mon, 6=Sun
    return ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][wd]


def fetch_weather():
    """Fetch 7-day forecast from Open-Meteo (no API key required)"""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude={}&longitude={}"
            "&current_weather=true"
            "&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max,uv_index_max,sunrise,sunset"
            "&temperature_unit=fahrenheit"
            "&wind_speed_unit=mph"
            "&timezone=America%2FChicago"
            "&forecast_days=7"
        ).format(LATITUDE, LONGITUDE)
        print("Fetching weather...")
        r = urequests.get(url, timeout=15)
        raw = r.json()
        r.close()

        cw = raw["current_weather"]
        daily = raw["daily"]
        return {
            "current_temp": cw["temperature"],
            "current_wind": cw["windspeed"],
            "current_code": cw["weathercode"],
            "current_is_day": cw["is_day"],
            "daily_dates": daily["time"],
            "daily_high": daily["temperature_2m_max"],
            "daily_low": daily["temperature_2m_min"],
            "daily_code": daily["weathercode"],
            "daily_precip": daily["precipitation_probability_max"],
            "uv_index": daily["uv_index_max"][0],
            "sunrise": daily["sunrise"][0][11:16],
            "sunset": daily["sunset"][0][11:16],
        }
    except Exception as e:
        print("Weather fetch failed: {}".format(e))
        return None


def draw_weather(weather, date_str, time_str, tz):
    """Render 7-day forecast dashboard"""
    graphics.set_pen(PEN_WHITE)
    graphics.clear()
    graphics.set_pen(PEN_BLACK)

    # Header
    graphics.text("WEATHER STATION", 20, 10, scale=4)
    graphics.text(
        "{}   {} {} {}".format(LOCATION_NAME, date_str, time_str, tz), 20, 42, scale=2
    )
    graphics.line(20, 66, WIDTH - 20, 66)

    if weather is None:
        graphics.set_pen(PEN_RED)
        graphics.text("ERROR", 200, 200, scale=6)
        graphics.set_pen(PEN_BLACK)
        graphics.text("Could not fetch weather data", 80, 320, scale=2)
        graphics.line(20, 440, WIDTH - 20, 440)
        graphics.text("Press B for servers", 220, 455, scale=2)
        graphics.update()
        return

    # Current conditions
    temp = weather["current_temp"]
    wind = weather["current_wind"]
    code = weather["current_code"]
    is_day = weather["current_is_day"]
    desc = weather_description(code)

    graphics.set_pen(PEN_BLUE)
    graphics.text("{}F".format(int(temp)), 20, 80, scale=7)

    # Right-side details aligned with the large temp block
    graphics.set_pen(PEN_BLACK)
    graphics.text(desc, 350, 90, scale=3)
    graphics.text("Wind: {} mph".format(int(wind)), 350, 130, scale=2)

    # Today high/low from daily[0]
    today_hi = int(weather["daily_high"][0])
    today_lo = int(weather["daily_low"][0])
    today_precip = weather["daily_precip"][0]
    graphics.text(
        "H:{}  L:{}  Precip: {}%".format(today_hi, today_lo, today_precip),
        350,
        158,
        scale=2,
    )

    # Separator before 7-day strip
    separator_line_y = 210
    graphics.line(20, separator_line_y, WIDTH - 20, separator_line_y)

    # 7-day forecast strip
    col_w = (WIDTH - 20) // 7  # ~111px per column
    strip_y = separator_line_y + 10

    for i in range(7):
        cx = 10 + i * col_w
        date = weather["daily_dates"][i]
        hi = int(weather["daily_high"][i])
        lo = int(weather["daily_low"][i])
        dcode = weather["daily_code"][i]
        precip = weather["daily_precip"][i]
        label = day_abbrev(date)
        cond = weather_description(dcode)

        # Day name — bold for today (i==0)
        if i == 0:
            graphics.set_pen(PEN_BLUE)
            label = "TODAY"
        else:
            graphics.set_pen(PEN_BLACK)
        graphics.text(label, cx + 4, strip_y, scale=2)

        # High / Low
        graphics.set_pen(PEN_RED)
        graphics.text("{}".format(hi), cx + 4, strip_y + 22, scale=2)
        graphics.set_pen(PEN_BLACK)
        graphics.text("/{}".format(lo), cx + 28, strip_y + 22, scale=2)

        # Condition
        graphics.set_pen(PEN_BLACK)
        graphics.text(cond[:6], cx + 4, strip_y + 46, scale=1)

        # Precip %
        graphics.set_pen(PEN_BLUE)
        graphics.text("{}%".format(precip), cx + 4, strip_y + 58, scale=1)

        # Column divider
        if i > 0:
            graphics.set_pen(PEN_BLACK)
            graphics.line(cx, strip_y - 2, cx, strip_y + 72)

    # UV / Sunrise / Sunset info bar
    uv = weather.get("uv_index", 0)
    rise = fmt_time_12h(weather.get("sunrise", "06:00"))
    sset = fmt_time_12h(weather.get("sunset", "19:00"))
    uvlbl = uv_label(uv)

    print(f"Strip y: {strip_y}")
    extra_info_y = strip_y + 80  # 300
    graphics.line(20, extra_info_y, WIDTH - 20, extra_info_y)
    graphics.set_pen(PEN_BLACK)
    graphics.text("UV: {} ({})".format(int(uv), uvlbl), 30, extra_info_y + 20, scale=2)
    graphics.text("Sunrise: {}".format(rise), 300, extra_info_y + 20, scale=2)
    graphics.text("Sunset: {}".format(sset), 560, extra_info_y + 20, scale=2)
    graphics.line(20, extra_info_y + 50, WIDTH - 20, extra_info_y + 50)
    graphics.text("Press B for servers", 270, extra_info_y + 100, scale=2)

    print("Weather display updated")
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
    # Black border
    graphics.set_pen(PEN_BLACK)
    graphics.rectangle(bar_x, bar_y, bar_w, bar_h)
    # White background inside
    graphics.set_pen(PEN_WHITE)
    graphics.rectangle(bar_x + 2, bar_y + 2, bar_w - 4, bar_h - 4)
    # Colored fill based on CPU %
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
    weather_data = fetch_weather()
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
                weather_data = fetch_weather()
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
                weather_data = fetch_weather()
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

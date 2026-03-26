import ujson
import utime
import network
import urequests
import gc
import machine
import epd2in9
from logger import Logger


def load_config():
    with open("config.json", "r") as f:
        return ujson.load(f)


CFG = load_config()
log = Logger(
    level=CFG.get("log_level", "INFO"),
    max_bytes=CFG.get("log_max_bytes", 32768)
)

# ScanSync ProcessStatus mapping
STATUS_MAP = {
    0: "Nicht bereit",
    1: "Metadaten",
    2: "OCR",
    3: "Dateiname",
    4: "Sync",
    5: "Fertig",
    -1: "Fehler",
}

W = 296
H = 128


# ============================================================
# Zeichenhelfer
# ============================================================

def draw_gray_sep(epd, y, x0=0, w=296):
    """2px dithered gray separator"""
    for row in range(2):
        offset = (y + row) % 2
        for x in range(offset + x0, x0 + w, 2):
            epd.pixel(x, y + row, 0)


def draw_progress_bar(epd, x, y, w, h, val, mx=5):
    epd.rect(x, y, w, h, 0)
    if val < 0:
        for i in range(0, w, 4):
            epd.line(x + i, y,
                     x + min(i + h, w - 1), y + h - 1, 0)
        return
    fw = int((w - 4) * min(val, mx) / mx)
    if fw > 0:
        epd.fill_rect(x + 2, y + 2, fw, h - 4, 0)


def draw_doc_icon(epd, x, y):
    """11x14 document"""
    epd.rect(x, y, 11, 14, 0)
    epd.line(x + 7, y, x + 10, y + 3, 0)
    epd.vline(x + 7, y, 4, 0)
    epd.hline(x + 7, y + 3, 4, 0)
    epd.hline(x + 2, y + 6, 4, 0)
    epd.hline(x + 2, y + 8, 7, 0)
    epd.hline(x + 2, y + 10, 5, 0)


def draw_check(epd, x, y):
    """10x10 checkmark"""
    for d in range(2):
        epd.line(x + 1, y + 5 + d, x + 3, y + 8 + d, 0)
        epd.line(x + 3, y + 8 + d, x + 9, y + 1 + d, 0)


def draw_cross(epd, x, y):
    """10x10 X mark"""
    for d in range(2):
        epd.line(x + d, y, x + 9 + d, y + 9, 0)
        epd.line(x + 9 + d, y, x + d, y + 9, 0)


def draw_clock(epd, x, y):
    """12x12 clock"""
    epd.rect(x, y, 12, 12, 0)
    epd.rect(x + 1, y + 1, 10, 10, 0)
    epd.line(x + 6, y + 6, x + 6, y + 3, 0)
    epd.line(x + 6, y + 6, x + 9, y + 6, 0)


def draw_gear(epd, x, y):
    """10x10 gear"""
    epd.rect(x + 2, y + 2, 6, 6, 0)
    epd.fill_rect(x + 3, y, 4, 2, 0)
    epd.fill_rect(x + 3, y + 8, 4, 2, 0)
    epd.fill_rect(x, y + 3, 2, 4, 0)
    epd.fill_rect(x + 8, y + 3, 2, 4, 0)


def draw_wifi_small(epd, x, y, ok, col=1):
    """8x9 wifi icon in given color"""
    # 3 arcs (bottom to top)
    epd.pixel(x + 3, y + 8, col)  # center dot
    epd.pixel(x + 4, y + 8, col)
    # arc 1
    epd.pixel(x + 2, y + 6, col)
    epd.pixel(x + 5, y + 6, col)
    epd.pixel(x + 1, y + 7, col)
    epd.pixel(x + 6, y + 7, col)
    # arc 2
    epd.pixel(x + 1, y + 4, col)
    epd.pixel(x + 6, y + 4, col)
    epd.pixel(x, y + 5, col)
    epd.pixel(x + 7, y + 5, col)
    # arc 3
    epd.pixel(x, y + 2, col)
    epd.pixel(x + 7, y + 2, col)
    epd.hline(x + 1, y + 1, 6, col)
    epd.hline(x + 2, y, 4, col)
    if not ok:
        epd.line(x + 1, y, x + 6, y + 8, col)


def draw_server_small(epd, x, y, ok, col=1):
    """8x9 server icon in given color"""
    epd.rect(x, y, 8, 4, col)
    epd.pixel(x + 2, y + 1, col)
    epd.rect(x, y + 5, 8, 4, col)
    epd.pixel(x + 2, y + 6, col)
    if not ok:
        epd.line(x + 1, y, x + 6, y + 8, col)


def draw_wifi_icon(epd, x, y, connected, rssi):
    """Signal strength bars (white on black header, 15x10px)"""
    if not connected:
        for d in range(2):
            epd.line(x + 2 + d, y + 1, x + 9 + d, y + 8, 1)
            epd.line(x + 9 + d, y + 1, x + 2 + d, y + 8, 1)
        return
    if rssi >= -50:
        bars = 4
    elif rssi >= -60:
        bars = 3
    elif rssi >= -70:
        bars = 2
    else:
        bars = 1
    heights = [3, 5, 7, 10]
    bar_w = 3
    gap = 1
    for i in range(4):
        bx = x + i * (bar_w + gap)
        h = heights[i]
        by = y + 10 - h
        if i < bars:
            epd.fill_rect(bx, by, bar_w, h, 1)


def trunc(text, n):
    if len(text) <= n:
        return text
    return text[:n - 2] + ".."


def fmt_ts(ts):
    try:
        p = ts.split(" ")
        d = p[0].split("-")
        t = p[1].split(":")
        return "{}.{}. {}:{}".format(d[2], d[1], t[0], t[1])
    except Exception:
        return ts[:16] if len(ts) > 16 else ts


def time_ago(ts):
    try:
        p = ts.split(" ")
        d = p[0].split("-")
        t = p[1].split(":")
        sec = int(float(t[2])) if len(t) > 2 else 0
        epoch = utime.mktime((
            int(d[0]), int(d[1]), int(d[2]),
            int(t[0]), int(t[1]), sec, 0, 0
        ))
        diff = utime.time() - epoch
        if diff < 0:
            return "jetzt"
        if diff < 60:
            return "{}s".format(diff)
        if diff < 3600:
            return "{}min".format(diff // 60)
        if diff < 86400:
            return "{}h{}m".format(
                diff // 3600, (diff % 3600) // 60)
        return "{}d".format(diff // 86400)
    except Exception:
        return ""


# ============================================================
# Boot-Screen
# ============================================================

def draw_boot(epd, msg, step=0, total=4, sub=""):
    epd.fill(0xff)
    epd.fill_rect(0, 0, W, 16, 0)
    epd.text("ScanSync", 4, 4, 1)
    epd.text("v1.0", W - 36, 4, 1)
    cx = max(0, (W - len(msg) * 8) // 2)
    epd.text(msg, cx, 38, 0)
    if sub:
        sx = max(0, (W - len(sub) * 8) // 2)
        epd.text(sub, sx, 52, 0)
    # 4 Kästchen mit genug Abstand fuer Labels
    pw = 12
    labels = ["Init", "WiFi", "Zeit", "Daten"]
    # Breite pro Slot = max label breite (5ch*8=40) -> 42px
    slot_w = 42
    bx = (W - total * slot_w) // 2
    by = 76
    for i in range(total):
        # Kästchen zentriert im Slot
        kx = bx + i * slot_w + (slot_w - pw) // 2
        if i < step:
            epd.fill_rect(kx, by, pw, pw, 0)
        elif i == step:
            epd.rect(kx, by, pw, pw, 0)
            epd.fill_rect(kx + 3, by + 3, pw - 6, pw - 6, 0)
        else:
            epd.rect(kx, by, pw, pw, 0)
        # Label zentriert unter Kästchen
        lw = len(labels[i]) * 8
        lx = bx + i * slot_w + (slot_w - lw) // 2
        epd.text(labels[i], max(0, lx), by + pw + 4, 0)


# ============================================================
# WiFi
# ============================================================

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        log.info("WLAN bereits verbunden: " + wlan.ifconfig()[0])
        return wlan
    ssid = CFG["wifi_ssid"]
    pw = CFG["wifi_password"]
    log.info("Verbinde mit WLAN: " + ssid)
    wlan.connect(ssid, pw)
    for _ in range(40):
        if wlan.isconnected():
            log.info("WLAN verbunden: " + wlan.ifconfig()[0])
            return wlan
        utime.sleep(0.5)
    log.error("WLAN-Verbindung fehlgeschlagen")
    return wlan


# ============================================================
# Zeitsync via ip2time.maexbert.de /api/v1/
# ============================================================

def sync_time():
    host = CFG.get("time_server", "ip2time.maexbert.de")
    url = "http://{}/api/v1/".format(host)
    try:
        resp = urequests.get(
            url,
            headers={"User-Agent": "ScanSync-Status-Pico/1.0"})
        body = resp.json()
        resp.close()
        if not body.get("success"):
            log.warning(
                "Zeitsync API: " + str(body.get("error", "")))
            return False
        lt = body["data"]["local_time"]
        # "2026-02-16T15:30:00.123456+01:00"
        date_str, rest = lt.split("T")
        time_str = rest[:8]  # "15:30:00"
        d = date_str.split("-")
        t = time_str.split(":")
        machine.RTC().datetime((
            int(d[0]), int(d[1]), int(d[2]), 0,
            int(t[0]), int(t[1]), int(t[2]), 0
        ))
        log.info("Zeit sync: {} {}".format(date_str, time_str))
        return True
    except Exception as e:
        log.error("Zeitsync fehlgeschlagen: " + str(e))
        return False


# ============================================================
# API-Abfrage
# ============================================================

def fetch_status():
    host = CFG.get("server_host", "server3")
    ip_fb = CFG.get("server_ip_fallback", "")
    port = CFG.get("server_port", 5001)
    path = CFG.get("api_path", "/api/status")
    for target in [host, ip_fb]:
        if not target:
            continue
        url = "http://{}:{}{}".format(target, port, path)
        try:
            log.debug("Anfrage: " + url)
            resp = urequests.get(
                url,
                headers={"User-Agent": "ScanSync-Status-Pico/1.0"})
            data = resp.json()
            resp.close()
            log.info("Status OK von " + target)
            return data
        except Exception as e:
            log.warning("{}: {}".format(target, str(e)))
    log.error("Kein Server erreichbar")
    return None


# ============================================================
# Dashboard rendern (296x128)
# ============================================================
#
# y=0-13:   BLACK HEADER "ScanSync | WiFi-Icon"
# y=15-23:  Stats: "10ok 3run 2err =15  O46s"
# y=25-34:  Stacked bar [done|active|fail]
# y=36-37:  gray sep
# y=39-88:  5 file rows (10px each)
# y=92-93:  gray sep
# y=95-105: Last completed timestamp + ago
# y=109:    line
# y=113-127: BLACK FOOTER "Upd HH:MM  W:OK S:OK"

def draw_stacked_bar(epd, x, y, w, h, done, active, fail, total):
    """Stacked bar: solid=done, dithered=active, hatched=fail"""
    epd.rect(x, y, w, h, 0)
    if total <= 0:
        return
    inner_w = w - 4
    d_w = int(inner_w * done / total)
    a_w = int(inner_w * active / total)
    f_w = int(inner_w * fail / total)
    ix = x + 2
    iy = y + 2
    ih = h - 4
    # Done: solid black
    if d_w > 0:
        epd.fill_rect(ix, iy, d_w, ih, 0)
    # Active: dithered (gray)
    if a_w > 0:
        for row in range(ih):
            off = row % 2
            for px in range(off, a_w, 2):
                epd.pixel(ix + d_w + px, iy + row, 0)
    # Failed: vertical hatching
    if f_w > 0:
        fx = ix + d_w + a_w
        for col in range(0, f_w, 2):
            epd.vline(fx + col, iy, ih, 0)


def fmt_time_short(ts):
    """'2024-06-01 12:00:00' -> '12:00'"""
    try:
        return ts.split(" ")[1][:5]
    except Exception:
        return "??:??"


def render_display(epd, data, wifi_ok, server_ok, rssi=0):
    epd.fill(0xff)

    # === HEADER y=0..13 ===
    epd.fill_rect(0, 0, W, 14, 0)
    epd.text("ScanSync", 4, 3, 1)
    draw_wifi_icon(epd, W - 17, 2, wifi_ok, rssi)

    # === NO DATA ===
    if data is None:
        if not wifi_ok:
            draw_cross(epd, W // 2 - 5, 35)
            epd.text("WiFi getrennt", W // 2 - 52, 50, 0)
        else:
            draw_cross(epd, W // 2 - 5, 35)
            epd.text("Server nicht", W // 2 - 48, 50, 0)
            epd.text("erreichbar", W // 2 - 40, 62, 0)
        epd.fill_rect(0, 113, W, 15, 0)
        t = utime.localtime()
        epd.text("Upd {:02d}:{:02d}".format(
            t[3], t[4]), 4, 117, 1)
        return

    n_done = data.get("processed_pdfs", 0)
    n_act = data.get("processing_pdfs", 0)
    n_fail = data.get("failed_pdfs", 0)
    n_total = data.get("total_pdfs", 0)
    avg_s = data.get("avg_processing_seconds", 0)
    cur_proc = data.get("currently_processing", [])
    recent = data.get("recent_files", [])

    # === STATS LINE y=15..23 ===
    # "10ok 3run 2err =15  O46s"
    draw_check(epd, 4, 15)
    epd.text(str(n_done), 16, 16, 0)
    gx = 16 + len(str(n_done)) * 8 + 6
    draw_gear(epd, gx, 15)
    epd.text(str(n_act), gx + 12, 16, 0)
    fx = gx + 12 + len(str(n_act)) * 8 + 6
    draw_cross(epd, fx, 15)
    epd.text(str(n_fail), fx + 12, 16, 0)
    # Total
    tx = fx + 12 + len(str(n_fail)) * 8 + 6
    epd.text("=" + str(n_total), tx, 16, 0)
    # Avg time
    if avg_s > 0:
        avg_i = int(avg_s)
        if avg_i >= 60:
            avg_t = "{}m{}s".format(avg_i // 60, avg_i % 60)
        else:
            avg_t = "{}s".format(avg_i)
        at = "O" + avg_t
        epd.text(at, W - len(at) * 8 - 4, 16, 0)
        # draw a small circle for Ø
        epd.hline(W - len(at) * 8 - 4 + 1, 16, 5, 0)
        epd.hline(W - len(at) * 8 - 4 + 1, 23, 5, 0)
        epd.vline(W - len(at) * 8 - 4, 17, 6, 0)
        epd.vline(W - len(at) * 8 - 4 + 6, 17, 6, 0)

    # === STACKED BAR y=26..35 ===
    draw_stacked_bar(epd, 4, 26, W - 8, 10,
                     n_done, n_act, n_fail, n_total)
    # Legend under bar: tiny markers
    # no text labels needed, icons above are legend

    # === GRAY SEP y=38 ===
    draw_gray_sep(epd, 38)

    # === UNIFIED FILE LIST y=41..79 (4 rows à 10px) ===
    # Merge active + recent, deduplicate by id, active first
    files = []
    seen_ids = set()
    for item in cur_proc:
        fid = item.get("id", id(item))
        if fid not in seen_ids:
            seen_ids.add(fid)
            files.append(item)
    for item in recent:
        fid = item.get("id", id(item))
        if fid not in seen_ids:
            seen_ids.add(fid)
            files.append(item)

    max_rows = 5
    if files:
        for idx in range(min(max_rows, len(files))):
            item = files[idx]
            yy = 41 + idx * 10
            sc = item.get("status_code", 0)
            # Icon
            if sc == 5:
                draw_check(epd, 4, yy)
            elif sc < 0:
                draw_cross(epd, 4, yy)
            elif sc >= 1 and sc <= 4:
                draw_gear(epd, 4, yy)
            else:
                draw_doc_icon(epd, 4, yy)
            # Status short tag (right-aligned)
            stags = {
                0: "NEW", 1: "META", 2: "OCR",
                3: "NAME", 4: "SYNC", 5: "OK", -1: "ERR"
            }
            tag = stags.get(sc, "?")
            tag_str = "[" + tag + "]"
            tag_x = W - len(tag_str) * 8 - 2
            max_fn = (tag_x - 16 - 8) // 8
            fn = trunc(item.get("file_name", "?"), max_fn)
            epd.text(fn, 16, yy + 1, 0)
            epd.text(tag_str, tag_x, yy + 1, 0)
    else:
        epd.text("Keine Dateien", 16, 50, 0)

    # === GRAY SEP y=92 ===
    draw_gray_sep(epd, 92)

    # === LAST COMPLETED y=95..105 ===
    comp_ts = data.get("latest_completed_timestamp", "")
    draw_clock(epd, 4, 95)
    if comp_ts:
        cf = fmt_ts(comp_ts)
        ago = time_ago(comp_ts)
        label = "Fertig: " + cf
        if ago:
            label += " (" + ago + ")"
        epd.text(trunc(label, 34), 20, 97, 0)
    else:
        epd.text("Fertig: ---", 20, 97, 0)

    # === LINE y=109 ===
    epd.hline(0, 109, W, 0)

    # === FOOTER y=113..127 ===
    epd.fill_rect(0, 113, W, 15, 0)
    t = utime.localtime()
    epd.text(
        "Upd {:02d}:{:02d}".format(t[3], t[4]),
        4, 117, 1)
    draw_wifi_small(epd, W - 26, 117, wifi_ok, 1)
    draw_server_small(epd, W - 13, 117, server_ok, 1)


def get_rssi(wlan):
    if wlan and wlan.isconnected():
        try:
            return wlan.status('rssi')
        except Exception:
            return -40
    return 0


# ============================================================
# Hauptprogramm
# ============================================================

def main():
    log.info("=== ScanSync Status Display ===")
    gc.collect()

    # 1. Display initialisieren
    try:
        epd = epd2in9.EPD_2in9_Landscape()
        epd.Clear(0xFF)
        log.info("Display OK")
    except Exception as e:
        log.error("Display-Init: " + str(e))
        machine.reset()

    # Boot Step 1: Init OK
    draw_boot(epd, "Display bereit", step=1)
    epd.display_Base(epd.buffer)

    # Boot Step 2: WiFi
    draw_boot(epd, "WiFi verbinden...", step=1,
              sub=CFG.get("wifi_ssid", ""))
    epd.init()
    epd.display_Base(epd.buffer)

    wlan = None
    wifi_ok = False
    try:
        wlan = connect_wifi()
        wifi_ok = wlan.isconnected()
    except Exception as e:
        log.error("WiFi: " + str(e))

    if wifi_ok:
        draw_boot(epd, "WiFi OK: " + wlan.ifconfig()[0],
                  step=2)
    else:
        draw_boot(epd, "WiFi FEHLER!", step=1,
                  sub="Kein Netzwerk")
    epd.init()
    epd.display_Base(epd.buffer)

    # Boot Step 3: Zeitsync
    if wifi_ok:
        draw_boot(epd, "Zeit synchronisieren...", step=2)
        epd.init()
        epd.display_Base(epd.buffer)
        time_ok = False
        try:
            time_ok = sync_time()
        except Exception as e:
            log.warning("Zeitsync: " + str(e))
        if time_ok:
            draw_boot(epd, "Zeit OK!", step=3)
        else:
            draw_boot(epd, "Zeit FEHLER", step=2,
                      sub="Weiter ohne Sync")
        epd.init()
        epd.display_Base(epd.buffer)

    # Boot Step 4: Datenabruf
    draw_boot(epd, "Lade Status...", step=3)
    epd.init()
    epd.display_Base(epd.buffer)

    data = None
    server_ok = False
    if wifi_ok:
        try:
            data = fetch_status()
            server_ok = data is not None
        except Exception as e:
            log.error("Erster Abruf: " + str(e))

    # Dashboard: Full Refresh als Basis fuer Partial Updates
    render_display(epd, data, wifi_ok, server_ok, get_rssi(wlan))
    epd.init()
    epd.display_Base(epd.buffer)
    log.info("Dashboard aktiv")

    # Hauptschleife
    prev_data = data
    full_cnt = 0
    tsync_cnt = 0
    interval = CFG.get("update_interval_s", 30)

    while True:
        try:
            gc.collect()

            # WiFi pruefen
            if wlan and not wlan.isconnected():
                log.warning("WiFi getrennt, reconnect...")
                wifi_ok = False
                try:
                    wlan = connect_wifi()
                    wifi_ok = wlan.isconnected()
                except Exception as e:
                    log.error("Reconnect: " + str(e))
            elif wlan:
                wifi_ok = wlan.isconnected()

            # Zeitsync alle 120 Zyklen (~60 Min)
            tsync_cnt += 1
            if wifi_ok and tsync_cnt >= 120:
                tsync_cnt = 0
                try:
                    sync_time()
                except Exception:
                    pass

            # Status abrufen
            data = None
            server_ok = False
            if wifi_ok:
                try:
                    data = fetch_status()
                    server_ok = data is not None
                except Exception as e:
                    log.error("Abfrage: " + str(e))

            # Update nur wenn noetig
            needs = data != prev_data
            if not server_ok and prev_data is not None:
                needs = True

            # Full refresh alle 20 Zyklen (~10 Min)
            full_cnt += 1
            force_full = full_cnt >= 20

            if needs or force_full:
                log.debug("Display-Update full={}".format(
                    force_full))
                try:
                    render_display(
                        epd, data, wifi_ok, server_ok,
                        get_rssi(wlan))
                    if force_full:
                        full_cnt = 0
                        epd.init()
                        epd.display_Base(epd.buffer)
                        log.info("Full refresh")
                    else:
                        epd.display_Base(epd.buffer)
                        epd.display_Partial(epd.buffer)
                except Exception as e:
                    log.error("Render: " + str(e))
                prev_data = data

        except Exception as e:
            log.error("Loop: " + str(e))
            try:
                epd.fill(0xff)
                epd.text("FEHLER!", 100, 50, 0)
                epd.text(str(e)[:34], 8, 68, 0)
                epd.display_Partial(epd.buffer)
            except Exception:
                pass

        utime.sleep(interval)


try:
    main()
except KeyboardInterrupt:
    log.info("Manuell gestoppt")
except Exception as e:
    log.error("Fatal: " + str(e))
    utime.sleep(5)
    machine.reset()

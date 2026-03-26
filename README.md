# ScanSync Status Display

A MicroPython status dashboard for [Raspberry Pi Pico W](https://www.raspberrypi.com/products/raspberry-pi-pico/) with a [Waveshare 2.9" e-Paper display](https://www.waveshare.com/wiki/Pico-ePaper-2.9) that shows real-time processing status from a ScanSync document pipeline.

```
┌──────────────────────────────────┐
│ ScanSync              ▂▄▆█      │  ← Header with WiFi signal
│ ✓10  ⚙3  ✗2  =15       Ø46s    │  ← Stats overview
│ [████████████▒▒▒░░]             │  ← Progress bar
│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│ ⚙ report_q1.pdf         [OCR]  │  ← File list with status
│ ⚙ invoice_2026.pdf      [META] │
│ ✓ scan_003.pdf           [OK]   │
│ ✗ broken.pdf             [ERR]  │
│ ✓ letter_feb.pdf         [OK]   │
│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│ 🕐 Fertig: 26.03. 14:02 (3min) │  ← Last completed
│─────────────────────────────────│
│ Upd 14:05              📶 🖥    │  ← Footer with status icons
└──────────────────────────────────┘
```

## Features

- **Live dashboard** — polls a ScanSync server API and renders document processing status on a 296×128 e-Paper display
- **Boot sequence** — animated 4-step boot screen (Init → WiFi → Time → Data) with progress indicators
- **Stacked progress bar** — visual breakdown of done / active / failed documents
- **File list** — shows up to 5 documents with status tags (`NEW`, `META`, `OCR`, `NAME`, `SYNC`, `OK`, `ERR`)
- **WiFi signal bars** — real-time RSSI-based signal strength indicator
- **Auto-refresh** — configurable update interval with partial display updates for fast, flicker-free refreshes
- **Full refresh cycle** — periodic full refresh to prevent e-Paper ghosting
- **Time sync** — automatic clock synchronization via HTTP time API
- **WiFi reconnect** — automatic reconnection on connection loss
- **Logging** — file-based logging with rotation and colored terminal output

## Hardware

| Component | Model |
|---|---|
| Microcontroller | Raspberry Pi Pico W |
| Display | Waveshare 2.9" e-Paper Module (296×128, black/white) |

The display connects via SPI to the Pico W using the default pin configuration:

| Function | GPIO |
|---|---|
| RST | 12 |
| DC | 8 |
| CS | 9 |
| BUSY | 13 |
| CLK | SPI(1) default |
| DIN | SPI(1) default |

## Getting Started

### Prerequisites

- Raspberry Pi Pico W with [MicroPython](https://micropython.org/download/RPI_PICO_W/) flashed
- Waveshare 2.9" e-Paper display connected via SPI
- A running [ScanSync](https://github.com/maxi07/ScanSync) server with the status API enabled
- A tool to upload files to the Pico, e.g. [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html), [Thonny](https://thonny.org/), or the [MicroPico VS Code extension](https://marketplace.visualstudio.com/items?itemName=paulober.pico-w-go)

### 1. Flash MicroPython

Download the latest MicroPython UF2 for [Pico W](https://micropython.org/download/RPI_PICO_W/) and flash it:

1. Hold the **BOOTSEL** button on the Pico W and connect it via USB
2. Drop the `.uf2` file onto the `RPI-RP2` drive
3. The Pico reboots automatically with MicroPython

### 2. Configure

Copy the example config and fill in your values:

```bash
cp config.example.json config.json
```

Edit `config.json`:

```json
{
    "wifi_ssid": "YOUR_WIFI",
    "wifi_password": "YOUR_PASSWORD",
    "server_host": "server3",
    "server_ip_fallback": "192.168.1.100",
    "server_port": 5001,
    "api_path": "/api/status",
    "update_interval_s": 30,
    "time_server": "ip2time.maexbert.de",
    "log_level": "INFO",
    "log_max_bytes": 32768
}
```

| Key | Description |
|---|---|
| `wifi_ssid` | Your WiFi network name |
| `wifi_password` | Your WiFi password |
| `server_host` | Hostname of the ScanSync server |
| `server_ip_fallback` | Fallback IP if hostname resolution fails |
| `server_port` | Port the ScanSync API listens on |
| `api_path` | API endpoint path |
| `update_interval_s` | Seconds between status polls |
| `time_server` | HTTP time sync server |
| `log_level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `log_max_bytes` | Max log file size before rotation |

### 3. Upload to Pico

Upload all project files to the Pico W's filesystem. With `mpremote`:

```bash
mpremote connect /dev/tty.usbmodem* cp main.py epd2in9.py logger.py config.json :
```

Or use Thonny / MicroPico to transfer the files.

### 4. Run

The display starts automatically on boot. To trigger a manual run:

```bash
mpremote connect /dev/tty.usbmodem* run main.py
```

The boot sequence will walk through Init → WiFi → Time Sync → Data Fetch, then enter the main dashboard loop.

## Project Structure

```
scansync-status/
├── main.py               # Application entry point, dashboard rendering, main loop
├── epd2in9.py            # Waveshare 2.9" e-Paper display driver
├── logger.py             # File & console logger with rotation
├── config.example.json   # Configuration template
├── config.json           # Local configuration (git-ignored)
└── README.md
```

## API Contract

The display expects the ScanSync server to respond on `GET /api/status` with JSON in this shape:

```json
{
    "total_pdfs": 15,
    "processed_pdfs": 10,
    "processing_pdfs": 3,
    "failed_pdfs": 2,
    "avg_processing_seconds": 46.2,
    "latest_completed_timestamp": "2026-03-26 14:02:00",
    "currently_processing": [
        {
            "id": 1,
            "file_name": "report_q1.pdf",
            "status_code": 2
        }
    ],
    "recent_files": [
        {
            "id": 2,
            "file_name": "scan_003.pdf",
            "status_code": 5
        }
    ]
}
```

### Status Codes

| Code | Tag | Meaning |
|---|---|---|
| 0 | `NEW` | Not yet processed |
| 1 | `META` | Extracting metadata |
| 2 | `OCR` | Running OCR |
| 3 | `NAME` | Generating filename |
| 4 | `SYNC` | Syncing to target |
| 5 | `OK` | Completed |
| -1 | `ERR` | Failed |

## License

This project includes the Waveshare e-Paper driver (`epd2in9.py`) which is licensed under the MIT License by Waveshare.

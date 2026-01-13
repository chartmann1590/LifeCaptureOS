# LifeCaptureOS ESP32-CAM Firmware

ESP-IDF firmware for ESP32-CAM that captures images on interval, stores them on SD card with thumbnails, and uploads to backend over Wi-Fi.

## Features

- **Story Mode**: Interval-based photo capture (configurable 10-3600 seconds)
- **Local Storage**: Organized DCIM structure on SD card with metadata
- **Thumbnail Generation**: Automatic thumbnail creation for each capture
- **BLE Control**: Full device provisioning and control over Bluetooth LE
- **Wi-Fi Upload**: Resumable chunked uploads directly to backend
- **Robust**: Offline-tolerant with queue and retry logic

## Hardware Requirements

- **ESP32-CAM** (AI-Thinker or similar)
- **microSD card** (64GB recommended, Class 10 or better)
- **FTDI programmer** (for initial flashing)
- **Power supply** (5V, 2A recommended)

### ESP32-CAM Pinout

```
Camera Pins: Pre-configured in lifecaptureos_config.h
SD Card Pins:
- MISO: GPIO 2
- MOSI: GPIO 15
- CLK:  GPIO 14
- CS:   GPIO 13

Programming:
- TX -> FTDI RX
- RX -> FTDI TX
- GND -> FTDI GND
- 5V -> FTDI 5V
- IO0 -> GND (during flash)
```

## Prerequisites

### 1. Install ESP-IDF

**Linux/macOS**:
```bash
mkdir -p ~/esp
cd ~/esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32
. ./export.sh
```

**Windows**:
Download ESP-IDF installer from: https://dl.espressif.com/dl/esp-idf/

Or use command line:
```bash
mkdir %USERPROFILE%\esp
cd %USERPROFILE%\esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
install.bat esp32
export.bat
```

Verify installation:
```bash
idf.py --version
# Should show ESP-IDF v5.x
```

### 2. Prepare SD Card

Format SD card as **FAT32**:
- Windows: Right-click > Format > FAT32
- Linux: `sudo mkfs.vfat -F 32 /dev/sdX1`
- macOS: Disk Utility > Erase > MS-DOS (FAT)

Insert into ESP32-CAM SD slot before powering on.

## Building

### 1. Clone repository

```bash
cd lifecaptureos-clone/firmware
```

### 2. Configure (Optional)

```bash
idf.py menuconfig
```

Key settings:
- **Component config > Camera configuration**: Verify pin mappings
- **Component config > ESP32-specific**: Enable PSRAM (required!)
- **Serial flasher config**: Set flash size to 4MB

### 3. Build

```bash
idf.py build
```

This compiles the firmware and generates `build/lifecaptureos-firmware.bin`.

## Flashing

### 1. Connect FTDI

```
ESP32-CAM    FTDI
---------    ----
    TX    -> RX
    RX    -> TX
   GND    -> GND
    5V    -> 5V
   IO0    -> GND (for flash mode)
```

### 2. Flash firmware

```bash
idf.py -p /dev/ttyUSB0 flash

# Windows: COM3, COM4, etc.
# macOS: /dev/cu.usbserial-*
```

### 3. Monitor output

```bash
idf.py -p /dev/ttyUSB0 monitor

# Exit monitor: Ctrl+]
```

**After flashing**: Disconnect IO0 from GND and press RESET button.

### 4. Combined flash + monitor

```bash
idf.py -p /dev/ttyUSB0 flash monitor
```

## First Boot

On first boot, you should see:

```
I (123) main: LifeCaptureOS Firmware 1.0.0 starting...
I (234) sd_storage: SD card mounted successfully
I (345) camera: Camera initialized successfully
I (456) ble_service: BLE service initialized
I (567) main: Device ID: lifecaptureos-aabbccdd
I (678) main: LifeCaptureOS firmware ready!
I (789) main: Waiting for BLE commands...
```

The device is now advertising as `LifeCaptureOS-XXXX` over BLE.

## Onboarding via Android App

1. Open Android app
2. Scan for devices
3. Connect to `LifeCaptureOS-XXXX`
4. Pair and bond (accept pairing request)
5. Enter Wi-Fi credentials
6. Enter backend URL and device token
7. Device will connect to Wi-Fi and start uploading

## Configuration

### Via BLE

All configuration is done via BLE commands from Android app:

- **Wi-Fi**: WIFI_PROVISION command
- **Backend**: SET_BACKEND command
- **Capture settings**: SET_CONFIG command
- **Start/Stop**: START_STORY / STOP_STORY commands

### Via NVS (Advanced)

Configuration is stored in NVS (Non-Volatile Storage). To reset:

```bash
idf.py erase-flash
idf.py flash
```

## SD Card Structure

```
/DCIM/LIFECAPTUREOS/
├── YYYY/
│   └── MM/
│       └── DD/
│           ├── IMG_<timestamp>_<counter>.jpg
│           ├── THM_<timestamp>_<counter>.jpg
│           └── META_<timestamp>_<counter>.json
└── index.jsonl
```

**Example**:
```
/DCIM/LIFECAPTUREOS/2025/01/10/
├── IMG_1704902400_0001.jpg   (1.2 MB)
├── THM_1704902400_0001.jpg   (15 KB)
└── META_1704902400_0001.json (512 bytes)
```

**Metadata JSON**:
```json
{
  "media_id": "IMG_1704902400_0001",
  "type": 0,
  "captured_at": 1704902400,
  "filename": "IMG_1704902400_0001.jpg",
  "thumb_filename": "THM_1704902400_0001.jpg",
  "size_bytes": 1234567,
  "thumb_size_bytes": 15360,
  "resolution": "1600x1200",
  "quality": 85,
  "upload_state": 0
}
```

## Troubleshooting

### Camera initialization failed

**Error**: `Camera init failed: 0x105`

**Solutions**:
1. Check camera cable is properly seated
2. Verify power supply is 5V 2A (insufficient power is common issue)
3. Enable PSRAM in menuconfig
4. Try lower resolution in code

### SD card not mounted

**Error**: `Failed to mount filesystem`

**Solutions**:
1. Verify SD card is formatted as FAT32
2. Check SD card pins are correct
3. Try different SD card (some cards are incompatible)
4. Use Class 10 or better card
5. Check wiring - SD pins share with camera, no shorts

### BLE not advertising

**Solutions**:
1. Check serial monitor for BLE init errors
2. Verify Bluetooth is not disabled in menuconfig
3. Try power cycle
4. Check if another BLE device is connected

### Wi-Fi won't connect

**Solutions**:
1. Check SSID and password via BLE GET_STATUS
2. Verify 2.4GHz network (ESP32 doesn't support 5GHz)
3. Check Wi-Fi range and signal strength
4. Some enterprise WPA2 networks may not work

### Out of memory errors

**Solutions**:
1. Enable PSRAM in menuconfig (required for camera)
2. Reduce JPEG quality
3. Use lower resolution
4. Check `idf.py size-components` for memory usage

## Development

### Code Structure

```
firmware/
├── main/
│   ├── main.c              # Entry point, main loop
│   ├── lifecaptureos_config.h      # Configuration constants
│   ├── sd_storage.c/h      # SD card DCIM management
│   ├── camera_capture.c/h  # Camera and thumbnails
│   ├── ble_service.c/h     # BLE GATT protocol
│   ├── wifi_upload.c/h     # HTTP upload client
│   └── config_manager.c/h  # NVS configuration
├── CMakeLists.txt
└── sdkconfig
```

### Adding Features

**Example: Add video capture**

1. Update `camera_capture.c` to support video encoding
2. Add video metadata to `media_metadata_t`
3. Update upload logic to handle larger files
4. Test thoroughly on hardware

### Logging

Set log level per component:

```c
esp_log_level_set("*", ESP_LOG_INFO);
esp_log_level_set("wifi", ESP_LOG_DEBUG);
esp_log_level_set("camera", ESP_LOG_VERBOSE);
```

Or via menuconfig: **Component config > Log output**

### Debugging

**Enable JTAG**: ESP32-CAM doesn't have JTAG pins broken out, so use ESP-PROG or:

**Use GDB over serial**:
```bash
idf.py openocd
idf.py gdb
```

**Print debug info**:
```c
ESP_LOGI(TAG, "Capturing: %s", filename);
ESP_LOGW(TAG, "Low memory: %u bytes free", esp_get_free_heap_size());
ESP_LOGE(TAG, "Failed: %s", esp_err_to_name(err));
```

## Performance

| Metric | Value |
|--------|-------|
| Capture time | 1-2 seconds |
| Thumbnail gen | 200-500 ms |
| SD write | 100-300 ms |
| Upload (2MB image) | 10-30 seconds (Wi-Fi dependent) |
| Power consumption | ~200mA active, ~50mA idle |
| Storage | ~1000 images per GB |

## Production Deployment

### 1. Enable security

- Use HTTPS for backend (esp_http_client supports TLS)
- Implement certificate pinning
- Encrypt sensitive NVS data

### 2. Optimize power

- Use deep sleep between captures
- Turn off camera between shots
- Reduce Wi-Fi TX power if close to AP

### 3. OTA updates

- Implement OTA update via BLE or Wi-Fi
- Use ESP-IDF OTA framework
- Always keep factory partition for recovery

### 4. Watchdog

- Enable task watchdog for main tasks
- Implement automatic reset on crashes

## License

MIT

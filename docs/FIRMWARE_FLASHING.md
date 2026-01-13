# ESP32-CAM Firmware Flashing Guide (PlatformIO)

This guide provides instructions for flashing the LifeCaptureOS firmware onto your ESP32-CAM using **PlatformIO**, which is the recommended and most streamlined method.

## 1. Hardware Setup (No Jumpers Required)

Most modern ESP32-CAM kits come with an **ESP32-CAM-MB** (Motherboard) adapter. 

- **Connection**: Simply plug the ESP32-CAM module into the MB adapter and connect it to your PC via a Micro-USB cable.
- **No Jumpers**: The MB adapter handles the `IO0` to `GND` bridging automatically when you trigger an upload, so no manual jumpers are required.
- **Power**: The MB adapter generally provides sufficient stable power for flashing and basic operation.

## 2. Software Setup

### 2.1 Install PlatformIO
1. **VS Code (Recommended)**:
   - Install [Visual Studio Code](https://code.visualstudio.com/).
   - Open the **Extensions** view (`Ctrl+Shift+X`).
   - Search for and install the **PlatformIO IDE** extension.
2. **PlatformIO Core (CLI)**:
   - If you prefer the command line, follow the [PlatformIO Core Installation Guide](https://docs.platformio.org/en/latest/core/installation.html).

## 3. Flashing the Firmware

### 3.1 Via VS Code
1. Open the project folder in VS Code.
2. Open the `firmware/` folder as a workspace or just navigate to it.
3. PlatformIO will automatically detect the `platformio.ini` file.
4. Click the **PlatformIO icon** in the sidebar (Ant head).
5. Under `esp32cam`, click **Upload and Monitor**.

### 3.2 Via CLI (PlatformIO Core)
Navigate to the `firmware` directory and run:

```bash
cd firmware
pio run -t upload -t monitor
```

> [!NOTE]
> PlatformIO will automatically download the necessary ESP-IDF framework, toolchains, and libraries on the first build. This may take a few minutes.

## 4. Verification

1. **Upload Progress**: You should see a progress bar reaching 100%.
2. **Serial Monitor**: After uploading, the monitor will open automatically.
3. **Boot Logs**: You should see:
   ```text
   I (123) main: LifeCaptureOS Firmware starting...
   I (234) main: Device ID: lifecapture-xxxx
   ```

## Troubleshooting

- **Port Not Found**: 
  - Ensure your USB cable supports data (some are charge-only).
  - Check `platformio.ini` to ensure `upload_port` matches your system's port (e.g., `COM9` on Windows).
- **Upload Failed**: 
  - Ensure the ESP32-CAM is firmly seated in the MB adapter.
  - Close other serial monitors (like Arduino IDE or Putty) that might be holding the port.
- **Boot Loop**:
  - This is often caused by insufficient power. While the MB adapter is usually fine, if you have high-draw peripherals attached, you may need a dedicated 5V power source.

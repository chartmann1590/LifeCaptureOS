# LifeCaptureOS Quick Start Guide

Get your LifeCaptureOS wearable camera system up and running in 30 minutes.

## Prerequisites Checklist

- [ ] ESP32-CAM with 64GB microSD card (formatted FAT32)
- [ ] USB-MB adapter or Micro-USB cable
- [ ] Android phone (8.0+)
- [ ] Node.js 18+ (for Web UI)
- [ ] FFmpeg (on server for Video Recaps)
- [ ] Computer for backend server
- [ ] Ollama server with `moondream` and `llama3` models

## Step 1: Setup Backend (10 min)

### 1.1 Install Ollama on your server

```bash
# On your AI server (can be same machine or remote)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull moondream
ollama list  # Verify moondream is installed
```

### 1.2 Setup backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Edit OLLAMA_BASE_URL to point to your Ollama server
```

Example `.env`:
```
OLLAMA_BASE_URL=http://your-ollama-ip:11434
OLLAMA_VISION_MODEL=moondream
```

### 1.3 Initialize database and create device

```bash
python -m app.main init-db
python -m app.main create-device lifecaptureos-001 "My Camera"
```

**IMPORTANT**: Save the device token that's printed. See [Device Setup Guide](docs/DEVICE_SETUP.md) for more details.

Example output:
```
Device Token: dev_tok_Rj8kL2mN9pQ3vX7zA1bC4dE6fG8hI0jK
```

### 1.4 Start backend

```bash
python -m app.main
# Server running on http://localhost:8000
```

Get your computer's IP address:
- Linux/Mac: `ifconfig` or `ip addr`
- Windows: `ipconfig`

Your backend URL will be: `http://<YOUR_IP>:8000`

## Step 2: Flash ESP32-CAM Firmware (10 min)

For a complete guide on wiring and flashing, see [FIRMWARE_FLASHING.md](docs/FIRMWARE_FLASHING.md).

### 2.1 Install PlatformIO

We recommend using the **PlatformIO IDE** extension for VS Code:

1. Install [VS Code](https://code.visualstudio.com/).
2. Open Extensions (`Ctrl+Shift+X`) and search for **PlatformIO**.
3. Install the extension.

Alternatively, install the **PIO Core CLI**:
`pip install platformio`

### 2.2 Prepare SD card

Format microSD card as **FAT32** and insert into ESP32-CAM.

### 2.3 Flash firmware

Connect your ESP32-CAM to your PC via the USB-MB adapter (no jumpers required).

Flash using PlatformIO:
```bash
cd firmware
pio run -t upload -t monitor
```

**After flashing**: The device will reset and start automatically.

You should see:
```
I (123) main: LifeCaptureOS Firmware 1.0.0 starting...
I (234) main: Device ID: lifecaptureos-aabbccdd
I (345) main: LifeCaptureOS firmware ready!
```

## Step 3: Install Android App (5 min)

### 3.1 Build and install

```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

Or open in Android Studio and click Run.

### 3.2 Grant permissions

On first launch, grant:
- Bluetooth permissions
- Location permission (required for BLE scanning)

## Step 4: Onboard Device (5 min)

### 4.1 Open app and scan

App will automatically scan for `LifeCaptureOS-XXXX` devices.

### 4.2 Connect and pair

1. Tap your device in the list
2. Accept Bluetooth pairing request on phone

### 4.3 Provision

Enter the following info:

**Wi-Fi**:
- SSID: Your Wi-Fi network name
- Password: Your Wi-Fi password

**Backend**:
- Backend URL: `http://your-backend-ip:8000` (use your actual IP!)
- Device Token: The token you saved from Step 1.3

Tap **Complete Setup**.

Device will:
1. Connect to Wi-Fi (takes ~5-10 seconds)
2. Test backend connection
3. Start uploading

## Step 5: Start Capturing! (1 min)

### 5.1 Start Story Mode

In the app Home screen, tap **Start Story Mode**.

Device will:
- Capture photo every 5 minutes (default)
- Save to SD card with thumbnail
- Upload to backend automatically

### 5.2 View in Gallery

Tap **View Gallery** to see thumbnails loaded from device over BLE.

### 5.3 Check backend

Visit `http://<YOUR_IP>:8000/` to access the Web Dashboard (after building).

## Step 6: Access Web UI (Optional, 5 min)

The backend includes a React-based dashboard for easier media browsing.

### 6.1 Build the UI
```bash
cd backend/webui
npm install
npm run build
```

### 6.2 View Dashboard
Open your browser to `http://<YOUR_IP>:8000`. You can now browse all your memories and device stats!

For more details, see the [Web UI Guide](docs/WEB_UI_GUIDE.md).

## Step 7: AI Intelligence (Optional, 5 min)

LifeCaptureOS automatically turns your photos into memories.

1.  **AI Memories**: Every photo is automatically captioned by `moondream`. Open the Web UI to see tags and searchable descriptions.
2.  **Daily Videos**: At 05:00 AM every day, the system generates a video "Recap" of your previous day. Check the "Memories" tab to watch them.
3.  **AI Chat**: Use the search bar in the Web UI to ask questions like "what did I do yesterday morning?" using natural language.

For more details, see the [AI Features Guide](docs/AI_FEATURES_GUIDE.md).

## Verification

Check everything is working:

1. **Device status** (in app Home):
   - Mode: `CAPTURING`
   - Wi-Fi: Connected
   - Upload Queue: Processing

2. **Backend** (in browser):
   - Visit `http://<YOUR_IP>:8000/health`
   - Should show all services healthy

3. **SD Card** (after a few captures):
   - Remove SD, check `/DCIM/LIFECAPTUREOS/2025/01/10/`
   - Should see IMG_*.jpg, THM_*.jpg, META_*.json files

## Troubleshooting

### Device won't connect to Wi-Fi

- Check SSID/password are correct
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check Wi-Fi range

### Backend unreachable

- Check firewall allows port 8000
- Verify IP address is correct
- Try `curl http://<IP>:8000/health` from another device

### No AI captions

- Check Ollama is running: `curl http://<OLLAMA_IP>:11434/api/tags`
- Verify moondream model is available
- Check backend logs for Ollama errors

### Camera not initializing

- Check camera cable is properly seated
- Verify PSRAM is enabled in firmware (should be default)
- Try different power supply (need 5V 2A minimum)

## Next Steps

- Adjust capture interval in Settings (10 sec - 1 hour)
- Customize JPEG quality
- Enable/disable auto-upload
- View AI-generated captions on backend
- Export media files

## Support

- Check component READMEs: `backend/`, `firmware/`, `android/`
- Review protocol specs: `docs/BLE_PROTOCOL.md`, `docs/UPLOAD_API.md`
- Check logs:
  - ESP32: Serial monitor (`pio run -t monitor`)
  - Backend: Console output
  - Android: Logcat (`adb logcat -s LifeCaptureOSBleManager`)

Happy capturing! 📸

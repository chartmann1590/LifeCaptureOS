# LifeCaptureOS Android App

Android app for controlling LifeCaptureOS ESP32-CAM device via BLE and browsing captured media.

## Features

- **BLE Onboarding**: Scan, pair, and provision device
- **Wi-Fi Configuration**: Set Wi-Fi credentials over BLE
- **Backend Setup**: Configure backend URL and device token
- **Device Control**: Start/stop capture, adjust settings
- **Gallery**: Browse timeline of captures using thumbnails over BLE
- **Offline-First**: Works without internet connection

## Requirements

- Android 8.0+ (API 26+)
- BLE-capable device
- Android Studio Hedgehog or later
- JDK 17

## Setup

### 1. Clone repository

```bash
cd lifecaptureos-clone/android
```

### 2. Open in Android Studio

- File > Open > Select `android/` directory
- Wait for Gradle sync to complete

### 3. Build

```bash
./gradlew assembleDebug
```

Or use Android Studio: Build > Build Bundle(s) / APK(s) > Build APK(s)

### 4. Install on device

**Via Android Studio**:
- Connect device via USB
- Enable Developer Options and USB Debugging
- Run > Run 'app'

**Via ADB**:
```bash
./gradlew installDebug

# Or manually:
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Architecture

### Tech Stack

- **Language**: Kotlin
- **UI**: Jetpack Compose + Material 3
- **Architecture**: MVVM with ViewModels
- **DI**: Hilt
- **BLE**: Nordic BLE Library
- **Async**: Coroutines + Flow
- **Navigation**: Jetpack Navigation Compose
- **Image Loading**: Coil

### Project Structure

```
app/src/main/
├── java/com/lifecaptureos/
│   ├── LifeCaptureOSApplication.kt        # Hilt application
│   ├── MainActivity.kt            # Main activity
│   ├── ble/
│   │   └── BleManager.kt          # BLE communication
│   └── ui/
│       ├── navigation/
│       │   └── Navigation.kt      # App navigation
│       ├── screens/
│       │   ├── onboarding/        # Onboarding flow
│       │   ├── home/              # Home screen
│       │   ├── gallery/           # Gallery screen
│       │   └── settings/          # Settings screen
│       └── theme/
│           └── Theme.kt           # Material theme
└── res/
    └── values/
        └── strings.xml
```

## Usage

### 1. First Launch - Onboarding

1. **Scan**: App scans for `LifeCaptureOS-XXXX` devices
2. **Connect**: Tap device to connect and pair
3. **Provision**:
   - Enter Wi-Fi SSID and password
   - Enter backend URL (e.g., `http://your-backend-ip:8000`)
   - Enter device token (from backend)
4. **Complete**: Device configures and connects to Wi-Fi

### 2. Home Screen

- View device status (mode, SD free, capture count, upload queue)
- Start/Stop Story Mode (interval capture)
- Navigate to Gallery or Settings

### 3. Gallery

- Browse thumbnails of captured media
- Thumbnails loaded over BLE from device
- View upload status for each item

### 4. Settings

- Adjust capture interval (10-3600 seconds)
- Set JPEG quality (10-100%)
- Enable/disable auto-upload
- Save settings to device via BLE

## BLE Protocol

### Service UUID
```
0000FF10-0000-1000-8000-00805F9B34FB
```

### Characteristics

| Characteristic | UUID | Purpose |
|---------------|------|---------|
| CMD | 0xFF11 | Send commands (Write) |
| RSP | 0xFF12 | Receive responses (Notify) |
| THM | 0xFF13 | Receive thumbnails (Notify) |

### Command Flow

1. **Connect** to device
2. **Pair/Bond** (OS handles this)
3. **Authenticate**: Send `AUTH` command, receive session token
4. **Commands**: All subsequent commands include session token

Example command:
```json
{
  "request_id": "uuid",
  "session_token": "token",
  "command": "GET_STATUS",
  "params": {}
}
```

Example response:
```json
{
  "request_id": "uuid",
  "ok": true,
  "error": null,
  "data": {
    "firmwareVersion": "1.0.0",
    "mode": "capturing",
    ...
  }
}
```

## Development

### Running Tests

```bash
./gradlew test           # Unit tests
./gradlew connectedCheck # Instrumented tests
```

### Debugging BLE

Enable verbose BLE logging in `BleManager.kt`:

```kotlin
private val TAG = "LifeCaptureOSBleManager"

override fun log(priority: Int, message: String) {
    Log.println(priority, TAG, message)
}
```

View logs:
```bash
adb logcat -s LifeCaptureOSBleManager
```

### Common Issues

**BLE not scanning**:
1. Check location permission granted (required for BLE on Android < 12)
2. Check Bluetooth enabled
3. Check app has BLUETOOTH_SCAN permission (Android 12+)

**Connection fails**:
1. Ensure device is advertising
2. Try bonding manually from system Bluetooth settings first
3. Check device is not already connected to another app
4. Clear Bluetooth cache: Settings > Apps > Bluetooth > Storage > Clear Data

**Pairing prompt doesn't appear**:
- Some devices require manual pairing from system settings first
- Try toggling Bluetooth off/on

## Permissions

### Required

- `BLUETOOTH` / `BLUETOOTH_ADMIN` (legacy)
- `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT` (Android 12+)
- `ACCESS_FINE_LOCATION` (for BLE scanning on Android < 12)

### Declared in Manifest

All permissions are declared in `AndroidManifest.xml`.

Runtime permissions (location) are requested in onboarding flow.

## Building for Release

### 1. Generate signing key

```bash
keytool -genkey -v -keystore lifecaptureos-release.jks \
  -alias lifecaptureos -keyalg RSA -keysize 2048 -validity 10000
```

### 2. Configure signing

Create `android/keystore.properties`:

```properties
storeFile=../lifecaptureos-release.jks
storePassword=YourStorePassword
keyAlias=lifecaptureos
keyPassword=YourKeyPassword
```

### 3. Build release APK

```bash
./gradlew assembleRelease
```

Output: `app/build/outputs/apk/release/app-release.apk`

### 4. Build App Bundle (for Play Store)

```bash
./gradlew bundleRelease
```

Output: `app/build/outputs/bundle/release/app-release.aab`

## Future Enhancements

- [ ] Background BLE reconnection
- [ ] Thumbnail caching on device
- [ ] Push notifications for upload status
- [ ] Export media to phone storage
- [ ] Share media to other apps
- [ ] Multi-device support
- [ ] Dark theme
- [ ] Tablet UI

## Troubleshooting

### App crashes on launch

Check logcat:
```bash
adb logcat *:E
```

Common causes:
- Missing Hilt configuration
- BLE permissions not granted
- Incompatible Android version

### BLE "Service not found"

- Device may not be running LifeCaptureOS firmware
- Check firmware is flashed and running
- Verify device is advertising (check serial monitor)

### Thumbnails not loading

- Ensure device has captured images
- Check BLE connection is stable
- Verify thumbnail transfer protocol implementation

## Contributing

- Follow Kotlin style guide
- Use Compose best practices
- Add ViewModels for all screens
- Write unit tests for business logic

## License

MIT

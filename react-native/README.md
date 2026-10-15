# LifeCaptureOS React Native (Expo)

Cross-platform Expo client that mirrors the native Android app. Runs in its own node_modules and npm cache to avoid touching global Node installs.

## Setup

```powershell
cd react-native
$env:npm_config_cache="$PWD/.npm-cache"   # keep npm cache local (recommended)
npm install
```

## Running

```powershell
cd react-native
$env:npm_config_cache="$PWD/.npm-cache"
$env:EXPO_OFFLINE="true"                  # optional: skip network fetches
npm start
```

Scan the QR with Expo Go on Android/iOS. Press `Ctrl+C` to stop Metro.

## Navigation
- Uses Expo Router (Stack) with screens: home, status/control, gallery, settings.
- Entry point: `expo-router/entry` (see `app/` folder).
- Gallery and status fetch from the backend when `EXPO_PUBLIC_BACKEND_URL` (and device token for media) are set.

## Environment

Create `.env` (see `.env.example`) to expose values to the app:

```
EXPO_PUBLIC_BACKEND_URL=http://localhost:8000
EXPO_PUBLIC_DEVICE_TOKEN=your_device_token
```

Only keys prefixed with `EXPO_PUBLIC_` are bundled to the client.

## Linting

```powershell
cd react-native
$env:npm_config_cache="$PWD/.npm-cache"
npm run lint
```

## Next Steps
- Add BLE provisioning + control hooks.
- Wire backend media list + thumbnails.
- Introduce navigation (Expo Router) for onboarding, status, gallery, settings.

# Device Setup and Token Generation

To securely connect your LifeCaptureOS device to the backend, you must generate a unique **Device Token**. This token is used by the ESP32-CAM to authenticate its uploads.

## 1. Setup the Backend Environment

Before generating a token, ensure your backend environment is active:

```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
```

## 2. Initialize the Database

If you haven't already, initialize the database to store device and media records:

```bash
python -m app.main init-db
```

## 3. Generate a Device Token

Use the CLI utility to create a new device entry and generate its token. Replace `<device_id>` with a unique ID for your camera (e.g., `camera-01`) and `<name>` with a friendly name.

```bash
python -m app.main create-device <device_id> "<name>"
```

### Example
```bash
python -m app.main create-device lifecapture-mvp "Living Room Camera"
```

### Example Output
```text
Device created successfully!
Device ID: lifecapture-mvp
Device Token: dev_tok_abc123...

Store this token securely. It will be used by the ESP32.
```

> [!IMPORTANT]
> **Keep your Device Token secret.** Anyone with this token can upload media to your backend as if they were your device.

## 4. Using the Token

You will need this token during the **Onboarding** phase of the Android app:

1. Copy the **Device Token** exactly as it appeared in the output.
2. In the LifeCaptureOS Android app, when prompted for the "Device Token", paste it into the field.
3. Complete the setup to save the token to the ESP32-CAM's permanent memory (NVS).

## Troubleshooting

- **"Command not found"**: Ensure you are in the `backend` directory and your virtual environment is activated.
- **Database errors**: Make sure you ran `init-db` at least once.
- **Lost Token**: If you lose a token, you can run the `create-device` command again with a new ID, or manually check the database (advanced).

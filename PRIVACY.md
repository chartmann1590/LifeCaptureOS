# Privacy Policy for LifeCaptureOS

LifeCaptureOS is designed with a **privacy-first, local-first** philosophy. This document explains how data is handled within the system.

## 1. Data Collection and Ownership

LifeCaptureOS (the firmware, Android app, and backend) is a self-hosted tool. 
- **Ownership**: You own 100% of the data captured by your device.
- **Media**: Photos and videos are stored locally on the device's microSD card and uploaded directly to your self-hosted backend server via Wi-Fi.
- **Metadata**: Information about capture times and device status is stored in your local backend database.

## 2. Data Processing

All AI analysis is performed using a local instance of **Ollama**.
- **Vision Analysis**: Images are sent to your specified Ollama instance (running models like `moondream`) for captioning and tagging.
- **Summarization**: Daily recaps are generated using the local AI and FFmpeg.
- **No Cloud Training**: By default, no data is sent to external cloud services for training or processing.

## 3. Data Storage

- **Device**: Media is stored on a FAT32 microSD card in an organized DCIM structure.
- **Backend**: Media is stored in your backend's filesystem, and metadata is stored in a local SQLite database.
- **Android App**: The app stores minimal data locally (cached thumbnails and configuration) and does not upload your data to any third-party servers.

## 4. Connectivity and Security

- **BLE**: Bluetooth Low Energy is used for initial setup and control commands. Session tokens are used to prevent unauthorized access.
- **Wi-Fi**: Media is uploaded directly to your backend URL. We recommend using HTTPS and a private network for these uploads.
- **Device Tokens**: Each device uses a unique token to authenticate with your backend.

## 5. Third-Party Services

LifeCaptureOS does not integrate with any third-party analytics or tracking services by default. The only external connection is to the Ollama instance you configure.

## 6. Your Controls

Since you host the backend and the Ollama instance, you have full control over your data. You can delete images, clear the database, or shut down the system at any time without needing permission from anyone.

---
*Last Updated: January 2026*

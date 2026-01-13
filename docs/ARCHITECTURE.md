# LifeCaptureOS System Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    LifeCaptureOS Ecosystem                    │
└──────────────────────────────────────────────────────────────┘

  ┌─────────────┐            BLE            ┌──────────────┐
  │  ESP32-CAM  │◄──────────────────────────►│   Android    │
  │  + SD Card  │   (Control + Thumbnails)   │     App      │
  └──────┬──────┘                            └──────────────┘
         │
         │ Wi-Fi (Direct Upload)
         │ Full-res images/videos
         │
         ▼
  ┌──────────────┐        HTTP API          ┌──────────────┐
  │   Backend    │◄────────────────────────►│   Remote     │
  │   Server     │    (Image Analysis)       │   Ollama     │
  │  (FastAPI)   │                           │ (moondream)  │
  └──────────────┘                           └──────────────┘
```

## Component Breakdown

### 1. ESP32-CAM Firmware (firmware/)

**Role**: Capture device that runs autonomously

**Key Responsibilities**:
- Capture photos on interval (Story Mode)
- Generate thumbnails locally
- Store media on SD card in organized structure
- Expose BLE GATT service for control
- Upload media to backend over Wi-Fi

**Technology Stack**:
- Language: C
- Framework: ESP-IDF 5.x
- Camera: ESP32-CAM (OV2640 sensor)
- Storage: FAT32 on microSD
- Connectivity: BLE + Wi-Fi

**Architecture**:
```
main.c
  ├─> config_manager.c   (NVS configuration)
  ├─> camera_capture.c   (Image capture + thumbnails)
  ├─> sd_storage.c       (DCIM file structure)
  ├─> ble_service.c      (GATT service + commands)
  └─> wifi_upload.c      (HTTP client + resume)
```

**Key Features**:
- Interval capture (10 sec - 1 hour configurable)
- Thumbnail generation (JPEG, ~15KB each)
- Resumable uploads with chunking
- Offline queue with retry logic
- BLE command protocol (JSON over GATT)

**Storage Structure**:
```
/DCIM/LIFECAPTUREOS/
  └─ 2025/01/10/
      ├─ IMG_1704902400_0001.jpg  (1.2MB)
      ├─ THM_1704902400_0001.jpg  (15KB)
      └─ META_1704902400_0001.json (metadata)
```

---

### 2. Android App (android/)

**Role**: Mobile control interface

**Key Responsibilities**:
- Onboard and provision device via BLE
- Browse device-local media timeline
- Control capture settings
- Monitor device status

**Technology Stack**:
- Language: Kotlin
- UI: Jetpack Compose + Material 3
- Architecture: MVVM + Hilt DI
- BLE: Nordic BLE Library
- Navigation: Navigation Compose

**Architecture**:
```
MainActivity
  └─> LifeCaptureOSNavHost (Navigation)
       ├─> OnboardingScreen (BLE scan + provision)
       ├─> HomeScreen (Status + controls)
       ├─> GalleryScreen (Thumbnail grid)
       └─> SettingsScreen (Configuration)

BleManager (Singleton)
  └─> Commands: AUTH, GET_STATUS, SET_CONFIG, LIST_MEDIA, etc.
```

**Key Features**:
- BLE device discovery and pairing
- Wi-Fi credential provisioning
- Backend URL configuration
- Thumbnail browsing over BLE
- Real-time device status
- Capture control (start/stop)

**BLE Protocol**:
- Service UUID: `0xFF10`
- CMD char: `0xFF11` (Write commands)
- RSP char: `0xFF12` (Receive responses)
- THM char: `0xFF13` (Thumbnail stream)

---

### 3. Backend Server (backend/)

**Role**: Media storage and AI analysis hub

**Key Responsibilities**:
- Receive resumable uploads from ESP32
- Store media with metadata in SQLite
- Run AI analysis via remote Ollama
- Provide REST API for media browsing

**Technology Stack**:
- Language: Python 3.11+
- Framework: FastAPI
- Database: SQLite (scalable to PostgreSQL)
- Storage: Filesystem (organized by device/date)
- AI: Remote Ollama (moondream vision model)

**Architecture**:
```
FastAPI App
  ├─> routers/
  │   ├─> device.py (Upload endpoints)
  │   └─> media.py (Browse endpoints)
  ├─> models.py (SQLAlchemy ORM)
  ├─> upload_service.py (Resumable upload logic)
  └─> ollama_service.py (AI integration)
```

**Database Schema**:
```sql
devices:
  - device_id, name, token_hash, last_seen

media:
  - id, device_id, media_id, type, captured_at
  - filename, media_path, thumb_path, size_bytes
  - upload_state, upload_progress
  - ai_caption, ai_tags_json, ai_confidence

upload_sessions:
  - upload_id, device_id, phase (metadata/media)
  - received_bytes, expected_size, expires_at
```

**Key Features**:
- Resumable chunked uploads (64KB chunks)
- Two-phase upload (metadata+thumb, then media)
- Background AI analysis on upload complete
- RESTful API with OpenAPI docs
- Device authentication (Bearer tokens)

**API Endpoints**:
```
Device (ESP32):
  POST /device/ping
  POST /device/media/initiate
  PUT  /device/media/{upload_id}/chunk
  GET  /device/media/{upload_id}/status
  POST /device/media/{upload_id}/complete

App/Web:
  GET /media/
  GET /media/{id}
  GET /media/{id}/thumb
  GET /media/{id}/file
  POST /media/{id}/reanalyze
```

---

### 4. Remote Ollama (External)

**Role**: AI vision model for image analysis

**Key Responsibilities**:
- Analyze uploaded images
- Generate captions
- Extract tags/objects

**Model**: moondream (vision-language model)

**Integration**:
- Backend calls Ollama HTTP API
- Sends base64-encoded images
- Receives structured captions + tags

**Example Analysis**:
```
Image → Ollama (moondream) → {
  "caption": "Person walking dog in park on sunny day",
  "tags": ["person", "dog", "park", "outdoor", "sunny"],
  "confidence": 0.92
}
```

---

## Data Flow

### Capture Flow

```
1. Timer expires (ESP32)
2. Camera captures JPEG
3. Generate thumbnail (scaled JPEG)
4. Save to SD:
   - IMG_xxx.jpg
   - THM_xxx.jpg
   - META_xxx.json
5. Add to upload queue
```

### Upload Flow

```
1. ESP32 initiates upload (POST /device/media/initiate)
   Phase: metadata
   Backend creates upload session

2. ESP32 uploads metadata + thumbnail in chunks
   PUT /device/media/{id}/chunk (multipart data)

3. ESP32 completes metadata phase
   POST /device/media/{id}/complete
   Backend extracts thumbnail, creates media record

4. ESP32 initiates media upload
   Phase: media

5. ESP32 uploads full image in 64KB chunks
   PUT /device/media/{id}/chunk (offset + data)
   (Resumable: can query status and continue)

6. ESP32 completes media upload
   POST /device/media/{id}/complete
   Backend triggers AI analysis (async)

7. Ollama analyzes image
   Backend stores caption + tags in DB
```

### BLE Control Flow

```
1. Android scans for BLE devices
2. User selects "LifeCaptureOS-XXXX"
3. Android connects + pairs
4. Android sends AUTH command
5. ESP32 generates session token
6. Android provisions:
   - WIFI_PROVISION (SSID, password)
   - SET_BACKEND (URL, token)
7. ESP32 connects to Wi-Fi
8. Android sends START_STORY
9. ESP32 begins interval capture
```

### Gallery Flow

```
1. Android sends LIST_MEDIA command over BLE
2. ESP32 returns list of media IDs + metadata
3. For each item, Android sends GET_THUMBNAIL
4. ESP32 streams thumbnail in chunks over BLE:
   - Chunk format: [transfer_id][chunk_idx][size][crc32][data]
5. Android reassembles chunks
6. Android displays thumbnail grid
```

---

## Security Model

### Device Authentication

**BLE**:
- Pairing/bonding required (PIN or Just Works)
- Session token after pairing (24h expiry)
- All commands include session token

**Wi-Fi Upload**:
- Bearer token authentication
- Device token provisioned during onboarding
- Backend validates token via hash lookup

**Token Flow**:
```
Backend creates device:
  token = generate_random_token()
  store hash(token) in database

User enters token in Android app

Android provisions ESP32 via BLE:
  SET_BACKEND(url, token)

ESP32 stores token in NVS

ESP32 uploads:
  Authorization: Bearer <token>

Backend validates:
  hash(received_token) == stored_hash
```

### Data Security

**At Rest**:
- SD card: No encryption (MVP)
- Backend storage: Filesystem permissions
- Database: SQLite file permissions

**In Transit**:
- BLE: Encrypted after pairing
- Wi-Fi: HTTP (MVP) or HTTPS (production)

**Production Recommendations**:
- Enable HTTPS with valid certificates
- Encrypt sensitive NVS data on ESP32
- Use PostgreSQL with proper access controls
- Implement rate limiting and abuse detection

---

## Scalability Considerations

### Current Limits (MVP)

- **Devices**: ~100 concurrent (SQLite bottleneck)
- **Media**: Unlimited (filesystem storage)
- **Uploads**: 1 per device (sequential)
- **AI Analysis**: Queue-based, 1 at a time

### Scaling Path

**For 1000+ devices**:

1. **Database**: Migrate to PostgreSQL
2. **Storage**: Use MinIO or S3-compatible object storage
3. **Upload**: Add Redis-backed task queue (Celery)
4. **AI**: Scale Ollama with multiple instances + load balancer
5. **Backend**: Run multiple FastAPI workers (Gunicorn/Uvicorn)
6. **Caching**: Add Redis for media list responses

**Architecture at Scale**:
```
           ┌─ FastAPI Worker 1
           ├─ FastAPI Worker 2
Load Bal ──┼─ FastAPI Worker 3
           └─ FastAPI Worker N
                    │
                    ├──> PostgreSQL
                    ├──> Redis (cache + queue)
                    ├──> MinIO (object storage)
                    └──> Ollama Cluster
```

---

## Development Workflow

### Adding a New Feature

**Example: Add burst capture mode**

1. **Update Protocol** (docs/BLE_PROTOCOL.md):
   - Add `START_BURST` command

2. **Firmware** (firmware/):
   - Add burst mode to `camera_capture.c`
   - Handle command in `ble_service.c`
   - Update `config_manager.c` for persistence

3. **Backend** (backend/):
   - Add burst metadata field to `models.py`
   - Update API schema if needed

4. **Android** (android/):
   - Add burst button to UI
   - Add `startBurst()` to `BleManager.kt`
   - Update `HomeViewModel.kt`

5. **Test**:
   - Flash firmware
   - Build Android app
   - Test end-to-end

### Testing Strategy

**Firmware**:
- Unit tests: Not practical for embedded (use serial monitor logs)
- Integration: Test on hardware with real SD card + camera
- BLE: Test with nRF Connect app or Android app

**Backend**:
- Unit tests: `pytest app/tests/`
- Integration: Test upload flow with mock ESP32 client
- API: Use OpenAPI docs (`/docs`) for manual testing

**Android**:
- Unit tests: ViewModels, data classes
- Instrumented: BLE connection flow
- Manual: Full onboarding on real device

---

## Performance Metrics

### ESP32-CAM

| Metric | Value |
|--------|-------|
| Capture time | 1-2 sec |
| Thumbnail gen | 200-500 ms |
| SD write | 100-300 ms |
| BLE throughput | ~10 KB/s (thumbnails) |
| Wi-Fi upload | ~200 KB/s (depends on signal) |
| Power consumption | ~200mA active, ~50mA idle |

### Backend

| Metric | Value (single instance) |
|--------|-------------------------|
| Upload latency | <100ms per chunk |
| AI analysis time | 2-5 sec per image (Ollama) |
| Concurrent uploads | 10-50 (depends on storage I/O) |
| Database queries | <10ms (SQLite w/ index) |

### Android

| Metric | Value |
|--------|-------|
| BLE scan time | 5-10 sec |
| Connection time | 2-5 sec |
| Thumbnail load | 1-2 sec per thumb |
| UI responsiveness | 60 FPS (Compose) |

---

## Maintenance

### Firmware OTA Updates

1. Build new firmware: `idf.py build`
2. Host binary on web server
3. ESP32 downloads and verifies (SHA256)
4. Writes to OTA partition
5. Reboots into new firmware

### Database Backups

```bash
# Backup SQLite
cp backend/data/app.db backend/data/app.db.backup

# Backup media (incremental)
rsync -av backend/data/media/ /backup/lifecaptureos/media/
```

### Monitoring

- **ESP32**: Serial logs via UART or BLE log characteristic
- **Backend**: Structured logging to stdout (capture with systemd or Docker)
- **Android**: Logcat for debugging

---

## Future Enhancements

### MVP+ Features

- [ ] Video capture support
- [ ] Live preview over BLE
- [ ] Encryption (E2E)
- [ ] Multi-device support in app
- [ ] Cloud sync option
- [ ] Web dashboard
- [ ] Advanced AI analysis (object detection, scene classification)

### Production Hardening

- [ ] Comprehensive error recovery
- [ ] Crash reporting (Sentry)
- [ ] Analytics (Mixpanel, PostHog)
- [ ] A/B testing framework
- [ ] Automated integration tests
- [ ] Load testing (Locust)
- [ ] Security audit

---

## License

MIT License - See LICENSE file for details.

---

## Contributors

Built with production-minded MVP philosophy: simple, reliable, extensible.

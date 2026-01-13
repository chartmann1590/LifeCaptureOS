# Upload API Specification

## Overview

The ESP32-CAM uploads media directly to the backend server over Wi-Fi using HTTP REST API. Uploads are resumable, chunked, and authenticated with device tokens.

## Authentication

All device API requests must include authentication header:

```
Authorization: Bearer <device_token>
```

The `device_token` is provisioned during onboarding and stored securely on the ESP32.

### Device Registration

Devices are pre-registered in the backend (via admin CLI or web UI). Each device gets:
- `device_id`: Unique identifier (e.g., "lifecaptureos-aabbccdd")
- `device_token`: Secret token for API auth (e.g., "dev_tok_abc123...")
- `name`: Human-friendly name (optional)

## Upload Flow

### Two-Phase Upload

Each media item requires **two upload sessions**:

1. **Metadata + Thumbnail** (small, ~10-50KB)
2. **Original Media** (large, 100KB-10MB+)

This allows the backend to:
- Show thumbnails quickly in the app
- Track upload progress per item
- Resume failed uploads efficiently

### Upload Session Lifecycle

```
1. Initiate Upload Session
   ↓
2. Upload Chunks (with resume support)
   ↓
3. Complete Session (finalize + verify)
   ↓
4. Trigger AI Analysis (async)
```

## API Endpoints

Base URL: `http://<backend-host>:8000`

### 1. Ping (Health Check)

**Endpoint**: `POST /device/ping`

**Description**: Verify connectivity and auth. Updates device last_seen timestamp.

**Request**:
```http
POST /device/ping HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
Content-Type: application/json

{
  "device_id": "lifecaptureos-aabbccdd",
  "firmware_version": "1.0.0",
  "status": {
    "uptime_seconds": 3600,
    "sd_free_mb": 45000,
    "capture_count": 1543,
    "queue_length": 12
  }
}
```

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "server_time": 1704902400,
  "device": {
    "id": "lifecaptureos-aabbccdd",
    "name": "My LifeCaptureOS Camera",
    "registered_at": 1704800000
  }
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid or missing token
- `404 Not Found`: Device not registered

---

### 2. Initiate Upload Session

**Endpoint**: `POST /device/media/initiate`

**Description**: Create a new upload session for metadata+thumbnail or original media.

**Request**:
```http
POST /device/media/initiate HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
Content-Type: application/json

{
  "device_id": "lifecaptureos-aabbccdd",
  "media_id": "IMG_1704902400_0001",
  "type": "image",
  "captured_at": 1704902400,
  "phase": "metadata",  // "metadata" or "media"
  "metadata": {
    "filename": "IMG_1704902400_0001.jpg",
    "resolution": "1600x1200",
    "quality": 85,
    "size_bytes": 2457600,
    "sha256": "a1b2c3..."  // Optional but recommended
  },
  "expected_size": 2457600
}
```

**Response**:
```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "ok": true,
  "upload_id": "upload_12345678",
  "session": {
    "chunk_size": 65536,  // 64KB chunks
    "received_bytes": 0,
    "expected_size": 2457600,
    "expires_at": 1704906000  // 1 hour from now
  },
  "resume_supported": true
}
```

**Parameters**:
- `phase`:
  - `"metadata"`: Upload thumbnail + metadata JSON
  - `"media"`: Upload original full-res file
- `type`: `"image"` or `"video"`
- `expected_size`: Total bytes to upload

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `400 Bad Request`: Invalid parameters
- `409 Conflict`: Upload session already exists (use resume)

---

### 3. Upload Chunk

**Endpoint**: `PUT /device/media/{upload_id}/chunk`

**Description**: Upload a chunk of data at specified offset. Supports resume.

**Request**:
```http
PUT /device/media/upload_12345678/chunk HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
Content-Type: application/octet-stream
Content-Range: bytes 0-65535/2457600
X-Chunk-CRC32: a1b2c3d4

<binary data>
```

**Headers**:
- `Content-Range`: `bytes <start>-<end>/<total>` (HTTP standard)
- `X-Chunk-CRC32`: Optional CRC32 of chunk data (hex)

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "received_bytes": 65536,
  "expected_size": 2457600,
  "progress": 2.67,
  "next_offset": 65536
}
```

**Resume Support**: Client can query current status and resume from `next_offset`.

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `404 Not Found`: Upload session not found or expired
- `400 Bad Request`: Invalid range or CRC mismatch
- `409 Conflict`: Offset mismatch (expected != received)

---

### 4. Query Upload Status

**Endpoint**: `GET /device/media/{upload_id}/status`

**Description**: Get current upload progress. Used for resume.

**Request**:
```http
GET /device/media/upload_12345678/status HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
```

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "upload_id": "upload_12345678",
  "device_id": "lifecaptureos-aabbccdd",
  "media_id": "IMG_1704902400_0001",
  "phase": "media",
  "received_bytes": 1310720,
  "expected_size": 2457600,
  "progress": 53.33,
  "next_offset": 1310720,
  "created_at": 1704902400,
  "updated_at": 1704902450,
  "expires_at": 1704906000
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `404 Not Found`: Upload session not found

---

### 5. Complete Upload Session

**Endpoint**: `POST /device/media/{upload_id}/complete`

**Description**: Finalize upload. Backend verifies size and checksum, then processes.

**Request**:
```http
POST /device/media/upload_12345678/complete HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
Content-Type: application/json

{
  "sha256": "a1b2c3d4e5f6...",  // Optional: full file hash
  "crc32": "a1b2c3d4"            // Optional: full file CRC32
}
```

**Response** (Metadata Phase):
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "phase": "metadata",
  "status": "completed",
  "media_id": "IMG_1704902400_0001",
  "next_step": "upload_media",
  "message": "Metadata and thumbnail received. Now upload original media."
}
```

**Response** (Media Phase):
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "phase": "media",
  "status": "completed",
  "media_id": "IMG_1704902400_0001",
  "media_record_id": 42,
  "analysis_queued": true,
  "storage": {
    "media_path": "media/lifecaptureos-aabbccdd/2025/01/10/IMG_1704902400_0001.jpg",
    "thumb_path": "thumbs/lifecaptureos-aabbccdd/2025/01/10/THM_1704902400_0001.jpg",
    "size_bytes": 2457600
  }
}
```

**Verification**:
- File size matches `expected_size`
- SHA256/CRC32 matches (if provided)
- File is readable and valid (basic check)

**Post-Completion**:
- For `media` phase: Triggers AI analysis job (async)
- Updates media record `upload_state` to `completed`

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `404 Not Found`: Upload session not found
- `400 Bad Request`: Incomplete upload (size mismatch) or verification failed

---

### 6. Abort Upload Session

**Endpoint**: `DELETE /device/media/{upload_id}`

**Description**: Cancel and clean up upload session.

**Request**:
```http
DELETE /device/media/upload_12345678 HTTP/1.1
Host: backend.example.com
Authorization: Bearer dev_tok_abc123...
```

**Response**:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "message": "Upload session aborted and cleaned up"
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `404 Not Found`: Upload session not found

---

### MVP Simple Upload (single request)

**Endpoint**: `POST /device/upload/image`

**Description**: Legacy/simple upload used by MVP firmware. Sends a full JPEG in
one request.

**Headers**:
- `Authorization: Bearer <device_token>`
- `Content-Type: image/jpeg`
- `X-Device-ID: <device_id>`
- `X-Media-ID: IMG_<timestamp>_<counter>`
- `X-Captured-At: <unix_epoch_seconds>` (optional but strongly recommended)

**Body**: Raw JPEG bytes

**Notes**:
- If `X-Captured-At` is missing or invalid, the backend uses upload time.
- `X-Media-ID` should include an epoch timestamp for reliable capture time
  recovery.

---

## Metadata+Thumbnail Upload Format

When `phase="metadata"`, the ESP32 uploads a **TAR archive** or **multipart form** containing:

### Option A: Multipart Form (Simpler)

```http
POST /device/media/upload_12345678/chunk HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary1234

------Boundary1234
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "media_id": "IMG_1704902400_0001",
  "type": "image",
  "captured_at": 1704902400,
  "filename": "IMG_1704902400_0001.jpg",
  "resolution": "1600x1200",
  "quality": 85,
  "size_bytes": 2457600,
  "sha256": "a1b2c3..."
}
------Boundary1234
Content-Disposition: form-data; name="thumbnail"; filename="thumbnail.jpg"
Content-Type: image/jpeg

<JPEG binary data>
------Boundary1234--
```

### Option B: Simple JSON + Binary (Recommended for ESP32)

**Chunk 0**: Metadata JSON
```json
{
  "media_id": "IMG_1704902400_0001",
  "type": "image",
  "captured_at": 1704902400,
  "filename": "IMG_1704902400_0001.jpg",
  "resolution": "1600x1200",
  "quality": 85,
  "size_bytes": 2457600,
  "thumbnail_size": 15360,
  "sha256": "a1b2c3..."
}
```

**Chunk 1+**: Thumbnail JPEG binary data

Backend parses first chunk as JSON, then reads thumbnail data from subsequent chunks.

---

## Upload Queue Management (ESP32)

### Queue Priority

1. **Metadata+Thumbnail** (high priority, small)
2. **Recent Media** (last 24h)
3. **Older Media** (backfill)

### Retry Strategy

```
Attempt   Delay
1         0s
2         5s
3         15s
4         45s
5         120s
...       max 300s (5 min)
```

After 10 consecutive failures, pause uploads for 1 hour.

### Network Efficiency

- **Batch small files**: If multiple items in queue, interleave metadata uploads
- **Large file chunking**: Use 64KB chunks (balance between overhead and resume granularity)
- **Concurrent uploads**: ESP32 should upload ONE file at a time (avoid memory issues)

---

## Backend Storage Structure

```
STORAGE_DIR/
├── media/
│   └── <device_id>/
│       └── <YYYY>/
│           └── <MM>/
│               └── <DD>/
│                   ├── IMG_<timestamp>_<counter>.jpg
│                   └── VID_<timestamp>_<counter>.mp4
└── thumbs/
    └── <device_id>/
        └── <YYYY>/
            └── <MM>/
                └── <DD>/
                    ├── THM_<timestamp>_<counter>.jpg
                    └── THM_<timestamp>_<counter>.jpg
```

---

## Security Considerations

### Device Token Security

- **Generation**: Use cryptographically random 32+ byte tokens
- **Storage**: ESP32 stores in NVS (encrypted if possible)
- **Rotation**: Support token rotation (new token invalidates old)
- **Revocation**: Admin can revoke tokens immediately

### HTTPS (Production)

For production deployments:
- Use HTTPS with valid certificates
- ESP32 validates server certificate (CA bundle or pinning)
- Prevents MITM attacks

For local/dev:
- HTTP acceptable if on trusted LAN
- Consider mTLS for paranoid setups

### Rate Limiting

Backend should implement:
- Max 100 requests/minute per device (normal operation)
- Max 10 upload initiations/minute per device
- Max 5 concurrent upload sessions per device

### Upload Validation

- **File Size Limits**:
  - Images: Max 10MB
  - Videos: Max 100MB
  - Thumbnails: Max 100KB
- **File Type Validation**:
  - Check magic bytes (JPEG: `FF D8 FF`, MP4: `00 00 00 xx 66 74 79 70`)
  - Reject executable/suspicious files
- **Path Traversal**:
  - Sanitize all filenames
  - Never use client-provided paths directly

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | OK | Continue |
| 201 | Created | Session created |
| 400 | Bad Request | Fix params, don't retry |
| 401 | Unauthorized | Re-provision token |
| 404 | Not Found | Session expired, restart |
| 409 | Conflict | Query status, resume |
| 413 | Payload Too Large | Split into smaller chunks |
| 429 | Too Many Requests | Backoff, retry later |
| 500 | Server Error | Retry with backoff |
| 503 | Service Unavailable | Retry with backoff |

### Client Retry Logic

```python
def should_retry(status_code):
    # Retry on network/server errors
    if status_code in [408, 429, 500, 502, 503, 504]:
        return True
    # Don't retry client errors
    if 400 <= status_code < 500:
        return False
    return True
```

---

## Testing Upload Flow

### cURL Examples

**1. Initiate Upload**:
```bash
curl -X POST http://localhost:8000/device/media/initiate \
  -H "Authorization: Bearer dev_tok_test123" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "lifecaptureos-test01",
    "media_id": "IMG_1704902400_0001",
    "type": "image",
    "captured_at": 1704902400,
    "phase": "media",
    "metadata": {
      "filename": "test.jpg",
      "resolution": "1600x1200",
      "size_bytes": 100000
    },
    "expected_size": 100000
  }'
```

**2. Upload Chunk**:
```bash
curl -X PUT http://localhost:8000/device/media/upload_12345678/chunk \
  -H "Authorization: Bearer dev_tok_test123" \
  -H "Content-Type: application/octet-stream" \
  -H "Content-Range: bytes 0-65535/100000" \
  --data-binary @chunk0.bin
```

**3. Complete Upload**:
```bash
curl -X POST http://localhost:8000/device/media/upload_12345678/complete \
  -H "Authorization: Bearer dev_tok_test123" \
  -H "Content-Type: application/json" \
  -d '{"sha256": "abc123..."}'
```

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Thumbnail upload (20KB) | < 5 seconds |
| Image upload (2MB) | < 30 seconds |
| Video upload (10MB) | < 2 minutes |
| Resume overhead | < 2 seconds |
| Concurrent devices | 100+ |

Assume:
- Wi-Fi: 2 Mbps upload (realistic for 2.4GHz)
- Backend: 1 Gbps network, SSD storage
- Database: SQLite (adequate for < 1000 devices)

---

## Future Enhancements

- **Delta uploads**: Only upload changed portions (for video)
- **Compression**: Optional gzip for metadata
- **Batch API**: Upload multiple small items in one request
- **WebSocket**: Real-time upload progress notifications
- **CDN integration**: Offload media serving to CDN

---

## Version History

- **v1.0** (2025-01): Initial upload API specification

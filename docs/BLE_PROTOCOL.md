# BLE Protocol Specification

## Overview

The ESP32-CAM exposes a custom BLE GATT service for device provisioning, control, and thumbnail browsing. All communication is secured with BLE pairing/bonding and session tokens.

## Security Model

1. **Pairing Required**: Device requires BLE bonding before accepting commands
2. **Session Token**: After pairing, client must establish session via `AUTH` command
3. **Command Authentication**: All commands include `session_token` in payload
4. **Session Expiry**: Sessions expire after 24 hours or device reboot

## GATT Service Definition

### Service UUID
```
Service: 0000FF10-0000-1000-8000-00805F9B34FB
```

### Characteristics

| Characteristic | UUID | Properties | Purpose |
|---------------|------|------------|---------|
| CMD | 0000FF11-0000-1000-8000-00805F9B34FB | Write | Send commands to device |
| RSP | 0000FF12-0000-1000-8000-00805F9B34FB | Notify | Receive responses and status |
| THM | 0000FF13-0000-1000-8000-00805F9B34FB | Notify | Receive thumbnail data chunks |
| LOG | 0000FF14-0000-1000-8000-00805F9B34FB | Notify | Optional: receive log messages |

## Message Format

All messages use JSON encoding (UTF-8). For large payloads (thumbnails), binary chunks are used.

### Command Format (CMD Characteristic)

```json
{
  "request_id": "uuid-v4",
  "session_token": "hex-string-or-null",
  "command": "COMMAND_NAME",
  "params": {
    // Command-specific parameters
  }
}
```

**Max size**: 512 bytes per write (split large commands if needed)

### Response Format (RSP Characteristic)

```json
{
  "request_id": "uuid-v4",
  "ok": true,
  "error": null,
  "data": {
    // Response-specific data
  }
}
```

**Chunking**: RSP payloads may be split across multiple notifications. Responses
are newline-delimited JSON; clients should buffer until a `\n` is received, then
parse each complete line as one response.

**Error response**:
```json
{
  "request_id": "uuid-v4",
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error"
  },
  "data": null
}
```

## Command Reference

### 1. AUTH - Establish Session

**Description**: Generate session token after pairing. No existing session required.

**Request**:
```json
{
  "request_id": "req-001",
  "session_token": null,
  "command": "AUTH",
  "params": {
    "client_id": "android-app-v1.0",
    "timestamp": 1704902400
  }
}
```

**Response**:
```json
{
  "request_id": "req-001",
  "ok": true,
  "error": null,
  "data": {
    "session_token": "a1b2c3d4e5f6...",
    "expires_at": 1704988800,
    "device_id": "lifecaptureos-aabbccdd"
  }
}
```

**Error codes**: `PAIRING_REQUIRED`, `AUTH_FAILED`

---

### 2. GET_STATUS - Device Status

**Description**: Get current device state.

**Request**:
```json
{
  "request_id": "req-002",
  "session_token": "a1b2c3...",
  "command": "GET_STATUS",
  "params": {}
}
```

**Response**:
```json
{
  "request_id": "req-002",
  "ok": true,
  "error": null,
  "data": {
    "firmware_version": "1.0.0",
    "device_id": "lifecaptureos-aabbccdd",
    "mode": "capturing",  // "idle" | "capturing" | "uploading" | "error"
    "uptime_seconds": 3600,
    "sd_card": {
      "mounted": true,
      "total_mb": 61440,
      "free_mb": 45000,
      "used_mb": 16440
    },
    "storage": {
      "auto_delete_24h": false
    },
    "wifi": {
      "connected": true,
      "ssid": "MyNetwork",
      "rssi": -65,
      "ip": "192.168.1.42"
    },
    "capture": {
      "total_count": 1543,
      "today_count": 87,
      "last_capture_timestamp": 1704902400,
      "interval_seconds": 300,
      "quality": 85,
      "resolution": "1600x1200"
    },
    "upload": {
      "queue_length": 12,
      "uploading": true,
      "last_upload_timestamp": 1704902350,
      "failed_count": 2
    },
    "battery": {
      "voltage_mv": 4150,
      "percentage": 85,
      "charging": false
    }
  }
}
```

**Error codes**: `SESSION_INVALID`, `DEVICE_ERROR`

---

### 2a. GET_CAPTURE_STATS - Capture Debug Stats

**Description**: Retrieve capture loop counters and last error for debugging.

**Request**:
```json
{
  "request_id": "req-002a",
  "session_token": "a1b2c3...",
  "command": "GET_CAPTURE_STATS",
  "params": {}
}
```

**Response**:
```json
{
  "request_id": "req-002a",
  "ok": true,
  "error": null,
  "data": {
    "attempts": 3,
    "successes": 2,
    "failures": 1,
    "timerTicks": 4,
    "lastCaptureTimestamp": 1704902400,
    "lastError": "CAPTURE_FAILED"
  }
}
```

**Error codes**: `SESSION_INVALID`

---

### 3. SET_CONFIG - Update Device Settings

**Description**: Update device configuration. Partial updates supported.

**Request**:
```json
{
  "request_id": "req-003",
  "session_token": "a1b2c3...",
  "command": "SET_CONFIG",
  "params": {
    "capture": {
      "interval_seconds": 180,      // Optional: 10-3600
      "quality": 90,                 // Optional: 10-100
      "resolution": "1600x1200",     // Optional: "1600x1200" | "800x600" | "640x480"
      "led_enabled": false,          // Optional
      "video_mode": false,           // Optional: enable video capture
      "video_duration_seconds": 10   // Optional: if video_mode=true
    },
    "upload": {
      "auto_upload": true,           // Optional
      "delete_after_upload": false,  // Optional: DANGEROUS
      "upload_on_wifi_only": true,   // Optional
      "retry_attempts": 5            // Optional: 1-10
    },
    "storage": {
      "auto_delete_24h": true        // Optional: auto-delete media older than 24h
    }
  }
}
```

**Response**:
```json
{
  "request_id": "req-003",
  "ok": true,
  "error": null,
  "data": {
    "updated": [
      "capture.interval_seconds",
      "capture.quality",
      "storage.auto_delete_24h"
    ],
    "reboot_required": false
  }
}
```

**Error codes**: `SESSION_INVALID`, `INVALID_PARAMS`, `VALUE_OUT_OF_RANGE`

---

### 4. WIFI_PROVISION - Configure Wi-Fi

**Description**: Set Wi-Fi credentials. Device will disconnect BLE briefly to test Wi-Fi.

**Request**:
```json
{
  "request_id": "req-004",
  "session_token": "a1b2c3...",
  "command": "WIFI_PROVISION",
  "params": {
    "ssid": "MyNetwork",
    "password": "SecurePassword123",
    "test_connection": true  // Optional: test before saving
  }
}
```

**Response**:
```json
{
  "request_id": "req-004",
  "ok": true,
  "error": null,
  "data": {
    "connected": true,
    "ip": "192.168.1.42",
    "rssi": -65
  }
}
```

**Error codes**: `SESSION_INVALID`, `WIFI_CONNECT_FAILED`, `INVALID_CREDENTIALS`

---

### 5. SET_BACKEND - Configure Backend

**Description**: Set backend server URL and device authentication token.

**Request**:
```json
{
  "request_id": "req-005",
  "session_token": "a1b2c3...",
  "command": "SET_BACKEND",
  "params": {
    "backend_url": "http://192.168.1.100:8000",
    "device_token": "dev_tok_abc123...",
    "device_id": "lifecaptureos-aabbccdd",
    "test_connection": true  // Optional: ping backend
  }
}
```

**Response**:
```json
{
  "request_id": "req-005",
  "ok": true,
  "error": null,
  "data": {
    "backend_reachable": true,
    "server_time": 1704902400
  }
}
```

**Error codes**: `SESSION_INVALID`, `BACKEND_UNREACHABLE`, `AUTH_FAILED`

---

### 6. START_STORY - Start Capture

**Description**: Begin interval capture (Story Mode).

**Request**:
```json
{
  "request_id": "req-006",
  "session_token": "a1b2c3...",
  "command": "START_STORY",
  "params": {}
}
```

**Response**:
```json
{
  "request_id": "req-006",
  "ok": true,
  "error": null,
  "data": {
    "mode": "capturing",
    "interval_seconds": 300,
    "started_at": 1704902400
  }
}
```

**Error codes**: `SESSION_INVALID`, `SD_NOT_MOUNTED`, `ALREADY_CAPTURING`

---

### 7. STOP_STORY - Stop Capture

**Description**: Stop interval capture.

**Request**:
```json
{
  "request_id": "req-007",
  "session_token": "a1b2c3...",
  "command": "STOP_STORY",
  "params": {}
}
```

**Response**:
```json
{
  "request_id": "req-007",
  "ok": true,
  "error": null,
  "data": {
    "mode": "idle",
    "stopped_at": 1704902400,
    "total_captured": 87
  }
}
```

**Error codes**: `SESSION_INVALID`, `NOT_CAPTURING`

---

### 8. LIST_MEDIA - List Captured Media

**Description**: Get paginated list of media items with metadata.

**Request**:
```json
{
  "request_id": "req-008",
  "session_token": "a1b2c3...",
  "command": "LIST_MEDIA",
  "params": {
    "limit": 50,           // Default: 50, Max: 1 (device clamps for BLE MTU)
    "offset": 0,           // Default: 0
    "sort": "newest",      // "newest" | "oldest"
    "type": "all"          // "all" | "image" | "video"
  }
}
```

**Response**:
```json
{
  "request_id": "req-008",
  "ok": true,
  "error": null,
  "data": {
    "total": 1543,
    "limit": 50,
    "offset": 0,
    "items": [
      {
        "id": "IMG_1704902400_0001",
        "type": "image",
        "capturedAt": 1704902400,
        "filename": "IMG_1704902400_0001.jpg",
        "thumbnail": null,
        "sizeBytes": 2457600,
        "thumbSizeBytes": 15360,
        "resolution": "1600x1200",
        "uploadState": "completed",  // "pending" | "uploading" | "completed" | "failed"
        "uploadProgress": 1
      }
      // ... more items
    ]
  }
}
```

**Error codes**: `SESSION_INVALID`, `SD_NOT_MOUNTED`, `INVALID_PARAMS`

---

### 9. GET_THUMBNAIL - Fetch Thumbnail

**Description**: Request thumbnail image. Data streamed over THM characteristic.

**Request**:
```json
{
  "request_id": "req-009",
  "session_token": "a1b2c3...",
  "command": "GET_THUMBNAIL",
  "params": {
    "media_id": "IMG_1704902400_0001"
  }
}
```

**Response** (RSP):
```json
{
  "request_id": "req-009",
  "ok": true,
  "error": null,
  "data": {
    "media_id": "IMG_1704902400_0001",
    "total_size": 15360,
    "chunk_size": 512,
    "total_chunks": 30,
    "transfer_id": "xfer-001"
  }
}
```

**Thumbnail Transfer** (THM characteristic):

After response, device sends chunks over THM characteristic. Each chunk:

```
Byte 0-3:   Transfer ID (uint32_t, little-endian)
Byte 4-5:   Chunk index (uint16_t, little-endian, 0-based)
Byte 6-7:   Chunk size (uint16_t, little-endian)
Byte 8-11:  CRC32 (uint32_t, little-endian, of data only)
Byte 12+:   JPEG data
```

**Client must**:
1. Enable notifications on THM characteristic
2. Collect chunks in order (or handle out-of-order)
3. Verify CRC32 of each chunk
4. Send ACK command after each chunk (or every N chunks)

**ACK Command**:
```json
{
  "request_id": "req-009-ack",
  "session_token": "a1b2c3...",
  "command": "THUMBNAIL_ACK",
  "params": {
    "transfer_id": "xfer-001",
    "chunk_index": 0,
    "status": "ok"  // "ok" | "crc_fail"
  }
}
```

**Error codes**: `SESSION_INVALID`, `MEDIA_NOT_FOUND`, `FILE_READ_ERROR`

---

### 10. DELETE_MEDIA - Delete Media Item

**Description**: Delete media from SD card. Requires `delete_enabled` config.

**Request**:
```json
{
  "request_id": "req-010",
  "session_token": "a1b2c3...",
  "command": "DELETE_MEDIA",
  "params": {
    "media_id": "IMG_1704902400_0001",
    "force": false  // Optional: delete even if not uploaded
  }
}
```

**Response**:
```json
{
  "request_id": "req-010",
  "ok": true,
  "error": null,
  "data": {
    "deleted": true,
    "freed_bytes": 2472960
  }
}
```

**Error codes**: `SESSION_INVALID`, `MEDIA_NOT_FOUND`, `DELETE_DISABLED`, `NOT_UPLOADED`

---

### 11. GET_LOGS - Retrieve Recent Logs

**Description**: Get ring buffer of recent log messages.

**Request**:
```json
{
  "request_id": "req-011",
  "session_token": "a1b2c3...",
  "command": "GET_LOGS",
  "params": {
    "lines": 100  // Default: 100, Max: 500
  }
}
```

**Response**:
```json
{
  "request_id": "req-011",
  "ok": true,
  "error": null,
  "data": {
    "logs": [
      "[1704902400] INFO: Capture started",
      "[1704902100] INFO: Wi-Fi connected",
      "[1704901800] WARN: Upload retry 1/5",
      "[1704901500] ERROR: SD write failed"
    ]
  }
}
```

**Error codes**: `SESSION_INVALID`

---

### 12. FACTORY_RESET - Reset Device

**Description**: Erase config and restart. Does NOT delete media.

**Request**:
```json
{
  "request_id": "req-012",
  "session_token": "a1b2c3...",
  "command": "FACTORY_RESET",
  "params": {
    "confirm": "RESET",
    "erase_media": false  // Optional: DANGEROUS
  }
}
```

**Response**:
```json
{
  "request_id": "req-012",
  "ok": true,
  "error": null,
  "data": {
    "resetting": true
  }
}
```

**Note**: Device will reboot after this command.

**Error codes**: `SESSION_INVALID`, `CONFIRMATION_REQUIRED`

---

### 13. CLEAR_STORAGE - Clear All Media

**Description**: Delete all media files from the SD card. Config is preserved.

**Request**:
```json
{
  "request_id": "req-013",
  "session_token": "a1b2c3...",
  "command": "CLEAR_STORAGE",
  "params": {
    "confirm": "CLEAR_ALL"
  }
}
```

**Response**:
```json
{
  "request_id": "req-013",
  "ok": true,
  "error": null,
  "data": {
    "cleared": true,
    "files_deleted": 1543,
    "freed_bytes": 104857600
  }
}
```

**Error codes**: `SESSION_INVALID`, `SD_NOT_MOUNTED`, `CONFIRMATION_REQUIRED`

---

## Error Codes Reference

| Code | Description |
|------|-------------|
| `PAIRING_REQUIRED` | BLE bonding not established |
| `SESSION_INVALID` | Session token missing, expired, or invalid |
| `AUTH_FAILED` | Authentication failed |
| `INVALID_PARAMS` | Invalid command parameters |
| `VALUE_OUT_OF_RANGE` | Parameter value outside allowed range |
| `WIFI_CONNECT_FAILED` | Wi-Fi connection failed |
| `BACKEND_UNREACHABLE` | Cannot reach backend server |
| `SD_NOT_MOUNTED` | SD card not available |
| `MEDIA_NOT_FOUND` | Media ID not found |
| `FILE_READ_ERROR` | Cannot read file from SD |
| `DELETE_DISABLED` | Delete not allowed by config |
| `NOT_UPLOADED` | Media not yet uploaded (delete blocked) |
| `ALREADY_CAPTURING` | Capture already in progress |
| `NOT_CAPTURING` | No capture in progress |
| `DEVICE_ERROR` | Internal device error |

## Implementation Notes

### For ESP32 Firmware

1. **BLE MTU Negotiation**: Request max MTU (512 bytes) for efficient transfers
2. **Chunk Size**: Use 512-byte chunks for thumbnails (fits in one BLE packet)
3. **Queue Commands**: Process commands sequentially; respond before executing long ops
4. **Keep-Alive**: Send periodic notifications on RSP for connection health
5. **Logging**: Use LOG characteristic for real-time debugging (optional)

### For Android App

1. **Connection Manager**: Implement reconnection logic with exponential backoff
2. **Command Queue**: Serialize commands; wait for response before next
3. **Thumbnail Cache**: Cache thumbnails locally; invalidate on device changes
4. **Progress UI**: Show transfer progress for large operations
5. **Timeout Handling**: 10s timeout for commands; 30s for thumbnail transfers

## Version History

- **v1.0** (2025-01): Initial protocol definition

## Future Extensions

- Compressed thumbnail transfer (JPEG baseline is already compact)
- Batch operations (delete multiple, list filters)
- Live preview streaming (MJPEG over BLE - challenging but possible)
- OTA firmware updates over BLE
- Encrypted payload option (AES-128-GCM)

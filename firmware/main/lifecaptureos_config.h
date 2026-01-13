/**
 * LifeCaptureOS Firmware Configuration
 */
#ifndef LIFECAPTUREOS_CONFIG_H
#define LIFECAPTUREOS_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

// Firmware version
#define FIRMWARE_VERSION "1.0.0"

// BLE Configuration
#define BLE_DEVICE_NAME_PREFIX "LifeCaptureOS-"
#define BLE_SERVICE_UUID        0xFF10
#define BLE_CHAR_CMD_UUID       0xFF11
#define BLE_CHAR_RSP_UUID       0xFF12
#define BLE_CHAR_THM_UUID       0xFF13
#define BLE_CHAR_LOG_UUID       0xFF14

// BLE Settings
#define BLE_MTU_SIZE           512
#define BLE_SESSION_TIMEOUT_MS (24 * 60 * 60 * 1000) // 24 hours
#define BLE_MAX_CMD_SIZE       512
#define BLE_THUMBNAIL_CHUNK_SIZE 508  // MTU - header overhead

// Camera Configuration (ESP32-CAM)
#define CAM_PIN_PWDN     32
#define CAM_PIN_RESET    -1
#define CAM_PIN_XCLK     0
#define CAM_PIN_SIOD     26
#define CAM_PIN_SIOC     27
#define CAM_PIN_D7       35
#define CAM_PIN_D6       34
#define CAM_PIN_D5       39
#define CAM_PIN_D4       36
#define CAM_PIN_D3       21
#define CAM_PIN_D2       19
#define CAM_PIN_D1       18
#define CAM_PIN_D0       5
#define CAM_PIN_VSYNC    25
#define CAM_PIN_HREF     23
#define CAM_PIN_PCLK     22

// SD Card Configuration
#define SD_MOUNT_POINT   "/sdcard"
#define SD_MAX_FILES     5  // Max open files
#define SD_PIN_MISO      2
#define SD_PIN_MOSI      15
#define SD_PIN_CLK       14
#define SD_PIN_CS        13

// DCIM Directory Structure
#define DCIM_BASE_PATH   SD_MOUNT_POINT "/DCIM/LIFECAPTUREOS"
#define DCIM_INDEX_FILE  SD_MOUNT_POINT "/DCIM/LIFECAPTUREOS/index.jsonl"

// Storage Configuration
#define MAX_FILENAME_LEN 128
#define MAX_PATH_LEN     256
#define MAX_MEDIA_ID_LEN 64

// Capture Defaults
#define DEFAULT_CAPTURE_INTERVAL_SEC  300    // 5 minutes
#define MIN_CAPTURE_INTERVAL_SEC      10
#define MAX_CAPTURE_INTERVAL_SEC      3600
#define DEFAULT_JPEG_QUALITY          85
#define MIN_JPEG_QUALITY              10
#define MAX_JPEG_QUALITY              100

// Upload Configuration
#define UPLOAD_CHUNK_SIZE          65536    // 64KB chunks
#define UPLOAD_MAX_RETRIES         5
#define UPLOAD_RETRY_DELAY_MS      5000
#define UPLOAD_TIMEOUT_MS          30000

// Memory Configuration
#define PSRAM_REQUIRED             true
#define THUMBNAIL_MAX_WIDTH        240
#define THUMBNAIL_MAX_HEIGHT       180
#define THUMBNAIL_QUALITY          70

// Queue Sizes
#define UPLOAD_QUEUE_SIZE          100
#define LOG_BUFFER_SIZE            500

// NVS Keys
#define NVS_NAMESPACE              "lifecaptureos"
#define NVS_KEY_WIFI_SSID          "wifi_ssid"
#define NVS_KEY_WIFI_PASS          "wifi_pass"
#define NVS_KEY_BACKEND_URL        "backend_url"
#define NVS_KEY_DEVICE_TOKEN       "device_token"
#define NVS_KEY_DEVICE_ID          "device_id"
#define NVS_KEY_CAPTURE_INTERVAL   "cap_interval"
#define NVS_KEY_JPEG_QUALITY       "jpg_quality"
#define NVS_KEY_AUTO_UPLOAD        "auto_upload"
#define NVS_KEY_DELETE_AFTER       "del_after"
#define NVS_KEY_AUTO_DELETE_24H    "auto_del24h"

#endif // LIFECAPTUREOS_CONFIG_H

/**
 * Wi-Fi Upload Client
 * Handles resumable uploads to backend server
 */
#ifndef WIFI_UPLOAD_H
#define WIFI_UPLOAD_H

#include <stdint.h>
#include <stdbool.h>
#include "sd_storage.h"

// Upload queue item
typedef struct {
    char media_id[MAX_MEDIA_ID_LEN];
    bool metadata_phase;  // true = upload metadata+thumb, false = upload media
    uint8_t retry_count;
} upload_queue_item_t;

// Wi-Fi functions
esp_err_t wifi_connect(const char *ssid, const char *password);
esp_err_t wifi_disconnect(void);
bool wifi_is_connected(void);
esp_err_t wifi_get_ip(char *out_ip, size_t max_len);

// Upload functions
esp_err_t upload_init(const char *backend_url, const char *device_token, const char *device_id);
esp_err_t upload_media_item(const media_metadata_t *metadata);
esp_err_t upload_process_queue(void);  // Process pending uploads

size_t upload_get_queue_length(void);

#endif // WIFI_UPLOAD_H

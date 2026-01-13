/**
 * BLE GATT Service
 * Implements the LifeCaptureOS control protocol over BLE
 */
#ifndef BLE_SERVICE_H
#define BLE_SERVICE_H

#include <stdint.h>
#include <stdbool.h>

// BLE service functions
esp_err_t ble_service_init(void);
esp_err_t ble_service_deinit(void);
bool ble_service_is_connected(void);

// Response sending
esp_err_t ble_send_response(const char *json_response);
esp_err_t ble_send_thumbnail_chunk(
    uint32_t transfer_id,
    uint16_t chunk_index,
    const uint8_t *data,
    uint16_t data_len,
    uint32_t crc32
);

// Get device ID for BLE advertising
void ble_get_device_id(char *out_id, size_t max_len);

#endif // BLE_SERVICE_H

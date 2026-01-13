/**
 * Configuration Manager
 * Handles NVS storage of device configuration
 */
#ifndef CONFIG_MANAGER_H
#define CONFIG_MANAGER_H

#include <stdint.h>
#include <stdbool.h>

// Device configuration
typedef struct {
    char wifi_ssid[33];
    char wifi_password[65];
    char backend_url[256];
    char device_token[256];
    char device_id[64];

    uint16_t capture_interval_sec;
    uint8_t jpeg_quality;
    bool auto_upload;
    bool delete_after_upload;
    bool auto_delete_24h;
} device_config_t;

esp_err_t lifecaptureos_config_init(void);
esp_err_t lifecaptureos_config_load(device_config_t *out_config);
esp_err_t lifecaptureos_config_save(const device_config_t *config);
esp_err_t lifecaptureos_config_factory_reset(void);

#endif // CONFIG_MANAGER_H

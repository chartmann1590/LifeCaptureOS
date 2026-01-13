/**
 * Configuration Manager Implementation
 */
#include <string.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"

#include "lifecaptureos_config.h"
#include "config_manager.h"

static const char *TAG = "config";

esp_err_t lifecaptureos_config_init(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    return ret;
}

esp_err_t lifecaptureos_config_load(device_config_t *out_config) {
    nvs_handle_t handle;
    esp_err_t err;

    err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "No saved config, using defaults");
        // Set defaults
        memset(out_config, 0, sizeof(device_config_t));
        out_config->capture_interval_sec = DEFAULT_CAPTURE_INTERVAL_SEC;
        out_config->jpeg_quality = DEFAULT_JPEG_QUALITY;
        out_config->auto_upload = true;
        out_config->delete_after_upload = false;
        out_config->auto_delete_24h = false;
        return ESP_OK;
    }

    // Load all config values
    size_t len;

    len = sizeof(out_config->wifi_ssid);
    nvs_get_str(handle, NVS_KEY_WIFI_SSID, out_config->wifi_ssid, &len);

    len = sizeof(out_config->wifi_password);
    nvs_get_str(handle, NVS_KEY_WIFI_PASS, out_config->wifi_password, &len);

    len = sizeof(out_config->backend_url);
    nvs_get_str(handle, NVS_KEY_BACKEND_URL, out_config->backend_url, &len);

    len = sizeof(out_config->device_token);
    nvs_get_str(handle, NVS_KEY_DEVICE_TOKEN, out_config->device_token, &len);

    len = sizeof(out_config->device_id);
    nvs_get_str(handle, NVS_KEY_DEVICE_ID, out_config->device_id, &len);

    uint16_t interval = DEFAULT_CAPTURE_INTERVAL_SEC;
    nvs_get_u16(handle, NVS_KEY_CAPTURE_INTERVAL, &interval);
    out_config->capture_interval_sec = interval;

    uint8_t quality = DEFAULT_JPEG_QUALITY;
    nvs_get_u8(handle, NVS_KEY_JPEG_QUALITY, &quality);
    out_config->jpeg_quality = quality;

    uint8_t auto_upload = 1; // Default true
    if (nvs_get_u8(handle, NVS_KEY_AUTO_UPLOAD, &auto_upload) != ESP_OK) {
        auto_upload = 1;
    }
    out_config->auto_upload = (bool)auto_upload;

    uint8_t delete_after_upload = 0;
    if (nvs_get_u8(handle, NVS_KEY_DELETE_AFTER, &delete_after_upload) != ESP_OK) {
        delete_after_upload = 0;
    }
    out_config->delete_after_upload = (bool)delete_after_upload;

    uint8_t auto_delete_24h = 0;
    if (nvs_get_u8(handle, NVS_KEY_AUTO_DELETE_24H, &auto_delete_24h) != ESP_OK) {
        auto_delete_24h = 0;
    }
    out_config->auto_delete_24h = (bool)auto_delete_24h;

    nvs_close(handle);

    ESP_LOGI(TAG, "Configuration loaded");
    return ESP_OK;
}

esp_err_t lifecaptureos_config_save(const device_config_t *config) {
    nvs_handle_t handle;
    esp_err_t err;

    err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }

    nvs_set_str(handle, NVS_KEY_WIFI_SSID, config->wifi_ssid);
    nvs_set_str(handle, NVS_KEY_WIFI_PASS, config->wifi_password);
    nvs_set_str(handle, NVS_KEY_BACKEND_URL, config->backend_url);
    nvs_set_str(handle, NVS_KEY_DEVICE_TOKEN, config->device_token);
    nvs_set_str(handle, NVS_KEY_DEVICE_ID, config->device_id);
    nvs_set_u16(handle, NVS_KEY_CAPTURE_INTERVAL, config->capture_interval_sec);
    nvs_set_u8(handle, NVS_KEY_JPEG_QUALITY, config->jpeg_quality);
    nvs_set_u8(handle, NVS_KEY_AUTO_UPLOAD, config->auto_upload ? 1 : 0);
    nvs_set_u8(handle, NVS_KEY_DELETE_AFTER, config->delete_after_upload ? 1 : 0);
    nvs_set_u8(handle, NVS_KEY_AUTO_DELETE_24H, config->auto_delete_24h ? 1 : 0);

    err = nvs_commit(handle);
    nvs_close(handle);

    ESP_LOGI(TAG, "Configuration saved");
    return err;
}

esp_err_t lifecaptureos_config_factory_reset(void) {
    nvs_flash_erase();
    nvs_flash_init();
    ESP_LOGI(TAG, "Factory reset completed");
    return ESP_OK;
}

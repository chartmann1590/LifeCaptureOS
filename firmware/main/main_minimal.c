/**
 * MINIMAL TEST - NO CAMERA, NO SD
 * Just logging + BLE to verify basic boot
 */
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "ble_service.h"
#include "config_manager.h"

static const char *TAG = "MINIMAL_TEST";

// Stub functions needed by BLE service
void start_capture(void) {
    ESP_LOGI(TAG, "start_capture() called (stub)");
}

void stop_capture(void) {
    ESP_LOGI(TAG, "stop_capture() called (stub)");
}

void app_apply_config(const device_config_t *config) {
    ESP_LOGI(TAG, "app_apply_config() called (stub)");
}

bool app_is_capture_active(void) {
    return false;
}

time_t app_get_last_capture_timestamp(void) {
    return 0;
}

uint32_t app_get_capture_attempts(void) {
    return 0;
}

uint32_t app_get_capture_successes(void) {
    return 0;
}

uint32_t app_get_capture_failures(void) {
    return 0;
}

const char *app_get_last_capture_error(void) {
    return "";
}

uint32_t app_get_capture_timer_ticks(void) {
    return 0;
}

void app_main(void) {
    // First thing - output to serial
    printf("\n\n=== MINIMAL TEST BOOT ===\n");
    printf("Serial output working!\n");

    ESP_LOGI(TAG, "=== MINIMAL TEST STARTING ===");
    ESP_LOGI(TAG, "Step 1: Init NVS");

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS erase needed");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "NVS initialized OK");

    ESP_LOGI(TAG, "Step 2: Init BLE");
    ret = ble_service_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "BLE init FAILED: %d", ret);
    } else {
        ESP_LOGI(TAG, "BLE initialized OK");

        char device_id[32];
        ble_get_device_id(device_id, sizeof(device_id));
        ESP_LOGI(TAG, "Device ID: %s", device_id);
    }

    ESP_LOGI(TAG, "=== MINIMAL TEST COMPLETE ===");
    ESP_LOGI(TAG, "Device should be visible in BLE now");

    // Main loop
    int counter = 0;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(5000));
        ESP_LOGI(TAG, "Heartbeat %d - still alive", counter++);
    }
}

/**
 * SIMPLE ESP32-CAM Firmware
 * Does ONLY what's needed - no complexity
 */
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "lifecaptureos_config.h"
#include "config_manager.h"
#include "sd_storage.h"
#include "camera_capture.h"
#include "ble_service.h"
#include "wifi_upload.h"

static const char *TAG = "main";

// Simple state
static device_config_t config;
static bool capturing = false;
static TimerHandle_t capture_timer = NULL;
static TaskHandle_t capture_task = NULL;

static void maybe_prune_storage(void) {
    if (!config.auto_delete_24h) {
        return;
    }

    time_t now = time(NULL);
    if (now <= 0) {
        return;
    }

    time_t cutoff = now - (24 * 60 * 60);
    size_t deleted = 0;
    uint64_t freed = 0;
    if (sd_delete_media_older_than(cutoff, &deleted, &freed) == ESP_OK && deleted > 0) {
        ESP_LOGI(TAG, "Auto-deleted %u files (%llu bytes)", (unsigned)deleted, (unsigned long long)freed);
    }
}

/**
 * Capture one photo and upload it
 */
static void do_capture(void) {
    ESP_LOGI(TAG, "Taking photo...");

    maybe_prune_storage();

    capture_config_t cap_config = {
        .width = 1600,
        .height = 1200,
        .quality = config.jpeg_quality,
        .led_enabled = false
    };

    capture_result_t result;
    if (camera_capture_image(&cap_config, &result) != ESP_OK || !result.success) {
        ESP_LOGE(TAG, "Capture failed");
        return;
    }

    // Save to SD
    media_metadata_t metadata;
    if (sd_create_media_entry(
        MEDIA_TYPE_IMAGE,
        time(NULL),
        result.image_data,
        result.image_len,
        result.thumbnail_data,
        result.thumbnail_len,
        config.jpeg_quality,
        result.resolution,
        &metadata
    ) != ESP_OK) {
        ESP_LOGE(TAG, "SD save failed");
        camera_free_result(&result);
        return;
    }

    ESP_LOGI(TAG, "Saved: %s", metadata.media_id);
    camera_free_result(&result);

    // Upload if WiFi connected
    ESP_LOGI(TAG, "Checking upload: connected=%d, auto_upload=%d", wifi_is_connected(), config.auto_upload);
    if (wifi_is_connected() && config.auto_upload) {
        upload_media_item(&metadata);
    }
}

/**
 * Capture task - waits for timer notifications
 */
static void capture_task_func(void *param) {
    while (1) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (capturing) {
            do_capture();
        }
    }
}

/**
 * Timer callback - triggers capture
 */
static void capture_timer_callback(TimerHandle_t timer) {
    if (capturing && capture_task) {
        xTaskNotifyGive(capture_task);
    }
}

/**
 * Start capturing
 */
void start_capture(void) {
    if (capturing) {
        ESP_LOGW(TAG, "Already capturing");
        return;
    }

    ESP_LOGI(TAG, "Starting capture (interval: %u sec)", config.capture_interval_sec);

    if (!capture_timer) {
        capture_timer = xTimerCreate(
            "capture",
            pdMS_TO_TICKS(config.capture_interval_sec * 1000),
            pdTRUE,
            NULL,
            capture_timer_callback
        );
    }

    if (!capture_timer || xTimerStart(capture_timer, 0) != pdPASS) {
        ESP_LOGE(TAG, "Timer start failed");
        return;
    }

    capturing = true;
    xTaskNotifyGive(capture_task); // Immediate first capture
    ESP_LOGI(TAG, "Capturing started");
}

/**
 * Stop capturing
 */
void stop_capture(void) {
    if (!capturing) return;

    ESP_LOGI(TAG, "Stopping capture");
    capturing = false;
    if (capture_timer) {
        xTimerStop(capture_timer, 0);
    }
}

/**
 * Upload worker - processes upload queue
 */
static void upload_task_func(void *param) {
    while (1) {
        if (wifi_is_connected() && config.auto_upload) {
            upload_process_queue();
        }
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}

/**
 * Apply new config
 */
void app_apply_config(const device_config_t *new_config) {
    if (!new_config) return;
    config = *new_config;

    // Update timer if capturing
    if (capture_timer && capturing) {
        xTimerChangePeriod(capture_timer,
            pdMS_TO_TICKS(config.capture_interval_sec * 1000), 0);
    }
}

bool app_is_capture_active(void) {
    return capturing;
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

/**
 * Main
 */
void app_main(void) {
    ESP_LOGI(TAG, "Starting...");

    // Init NVS
    ESP_ERROR_CHECK(nvs_flash_init());

    // Load config
    ESP_ERROR_CHECK(lifecaptureos_config_init());
    lifecaptureos_config_load(&config);

    // Init SD card
    ESP_LOGI(TAG, "Initializing SD card...");
    if (sd_storage_init() != ESP_OK) {
        ESP_LOGE(TAG, "SD init failed!");
    }

    // Init camera
    ESP_LOGI(TAG, "Initializing camera...");
    if (camera_init() != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed!");
    }

    // Init BLE
    ESP_ERROR_CHECK(ble_service_init());

    char device_id[32];
    ble_get_device_id(device_id, sizeof(device_id));
    ESP_LOGI(TAG, "Device: %s", device_id);

    // Connect WiFi if configured
    if (strlen(config.wifi_ssid) > 0) {
        wifi_connect(config.wifi_ssid, config.wifi_password);
    }

    // Init upload if backend configured
    if (strlen(config.backend_url) > 0) {
        upload_init(config.backend_url, config.device_token, device_id);
    }

    // Start tasks
    xTaskCreate(capture_task_func, "capture", 12288, NULL, 6, &capture_task);
    xTaskCreate(upload_task_func, "upload", 12288, NULL, 5, NULL);

    ESP_LOGI(TAG, "Ready! Waiting for BLE commands...");

    // Main loop does nothing
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

/**
 * Wi-Fi and Upload Implementation (MVP Stub)
 *
 * Full implementation includes:
 * - Wi-Fi event handling and reconnection
 * - HTTP client for resumable uploads
 * - Queue management with persistence
 * - Retry logic with exponential backoff
 */
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "nvs_flash.h"
#include "esp_sntp.h"
#include "cJSON.h"

#include "lifecaptureos_config.h"
#include "wifi_upload.h"

static const char *TAG = "wifi_upload";

static bool wifi_connected_flag = false;
static bool wifi_initialized = false;
static bool wifi_handlers_registered = false;
static esp_netif_t *wifi_netif = NULL;
static char backend_url[256] = {0};
static char device_token[256] = {0};
static char device_id[64] = {0};
static bool time_sync_in_progress = false;
static bool time_synced = false;

static void sntp_sync_task(void *param) {
    (void)param;

    sntp_setoperatingmode(SNTP_OPMODE_POLL);
    sntp_setservername(0, "pool.ntp.org");
    sntp_init();

    time_t now = 0;
    struct tm timeinfo = {0};
    int retry = 0;
    const int retry_count = 10;
    while (timeinfo.tm_year < (2016 - 1900) && ++retry <= retry_count) {
        ESP_LOGI(TAG, "Waiting for SNTP time sync... (%d/%d)", retry, retry_count);
        vTaskDelay(pdMS_TO_TICKS(2000));
        time(&now);
        gmtime_r(&now, &timeinfo);
    }

    if (timeinfo.tm_year >= (2016 - 1900)) {
        char formatted[32];
        strftime(formatted, sizeof(formatted), "%Y-%m-%d %H:%M:%S", &timeinfo);
        ESP_LOGI(TAG, "Time synced: %s UTC", formatted);
        time_synced = true;
    } else {
        ESP_LOGW(TAG, "Time sync failed; timestamps may be inaccurate");
    }

    time_sync_in_progress = false;
    vTaskDelete(NULL);
}

static void start_time_sync(void) {
    if (time_synced || time_sync_in_progress) {
        return;
    }
    time_sync_in_progress = true;
    xTaskCreate(sntp_sync_task, "sntp_sync", 4096, NULL, 5, NULL);
}

/**
 * Wi-Fi event handler
 */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                                 int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_connected_flag = false;
        ESP_LOGI(TAG, "Wi-Fi disconnected, retrying...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {     
        ip_event_got_ip_t *event = (ip_event_got_ip_t *) event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        wifi_connected_flag = true;
        start_time_sync();
    }
}

/**
 * Connect to Wi-Fi
 */
esp_err_t wifi_connect(const char *ssid, const char *password) {
    ESP_LOGI(TAG, "Connecting to Wi-Fi: %s", ssid);

    // Initialize networking once to avoid aborting on repeated provisioning
    if (!wifi_initialized) {
        esp_err_t err = esp_netif_init();
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "esp_netif_init failed: %s", esp_err_to_name(err));
            return err;
        }

        err = esp_event_loop_create_default();
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "event_loop_create_default failed: %s", esp_err_to_name(err));
            return err;
        }

        if (!wifi_netif) {
            wifi_netif = esp_netif_create_default_wifi_sta();
        }

        wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
        err = esp_wifi_init(&cfg);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "esp_wifi_init failed: %s", esp_err_to_name(err));
            return err;
        }

        wifi_initialized = true;
    }

    if (!wifi_handlers_registered) {
        esp_err_t err = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "wifi event handler register failed: %s", esp_err_to_name(err));
            return err;
        }

        err = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "ip event handler register failed: %s", esp_err_to_name(err));
            return err;
        }

        wifi_handlers_registered = true;
    }

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, ssid, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, password, sizeof(wifi_config.sta.password) - 1);

    esp_err_t err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_mode failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_config failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_wifi_start();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "esp_wifi_start failed: %s", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

bool wifi_is_connected(void) {
    return wifi_connected_flag;
}

/**
 * Initialize upload client
 */
esp_err_t upload_init(const char *url, const char *token, const char *dev_id) {
    strncpy(backend_url, url, sizeof(backend_url) - 1);
    strncpy(device_token, token, sizeof(device_token) - 1);
    strncpy(device_id, dev_id, sizeof(device_id) - 1);

    ESP_LOGI(TAG, "Upload client initialized for backend: %s", backend_url);
    return ESP_OK;
}

/**
 * Upload media item (metadata + thumbnail + full media)
 */
esp_err_t upload_media_item(const media_metadata_t *metadata) {
    ESP_LOGI(TAG, "Attempting upload for %s. WiFi: %d", metadata->media_id, wifi_connected_flag);
    
    if (!wifi_connected_flag) {
        ESP_LOGW(TAG, "Cannot upload: Wi-Fi not connected");
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Starting upload for: %s", metadata->media_id);

    // 1. Prepare URL: <backend_url>/device/upload/image
    // We assume a simple endpoint for MVP.
    char url[300];
    int printed = snprintf(url, sizeof(url), "%s/device/upload/image", backend_url);
    if (printed >= sizeof(url)) {
        ESP_LOGE(TAG, "URL too long");
        return ESP_FAIL;
    }

    // 2. Open file
    FILE *f = fopen(metadata->full_path, "rb");
    if (!f) {
        ESP_LOGE(TAG, "Failed to open file: %s", metadata->full_path);
        return ESP_FAIL;
    }

    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (file_size <= 0) {
        ESP_LOGE(TAG, "File empty: %s", metadata->full_path);
        fclose(f);
        return ESP_FAIL;
    }

    // 3. Configure HTTP Client
    esp_http_client_config_t config = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 30000,
        .buffer_size_tx = 4096,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "Failed to init HTTP client");
        fclose(f);
        return ESP_FAIL;
    }

    // Headers
    char auth_header[300];
    snprintf(auth_header, sizeof(auth_header), "Bearer %s", device_token);
    esp_http_client_set_header(client, "Authorization", auth_header);
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_header(client, "X-Device-ID", device_id);
    esp_http_client_set_header(client, "X-Media-ID", metadata->media_id);
    char captured_at_header[32];
    snprintf(captured_at_header, sizeof(captured_at_header), "%ld", (long)metadata->captured_at);
    esp_http_client_set_header(client, "X-Captured-At", captured_at_header);

    // 4. Perform Upload
    esp_err_t err = esp_http_client_open(client, file_size);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open HTTP connection: %s", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        fclose(f);
        return err;
    }

    // Send in chunks
    uint8_t *buffer = malloc(4096);
    if (!buffer) {
        ESP_LOGE(TAG, "OOM for upload buffer");
        esp_http_client_cleanup(client);
        fclose(f);
        return ESP_ERR_NO_MEM;
    }

    size_t total_sent = 0;
    while (total_sent < file_size) {
        size_t read = fread(buffer, 1, 4096, f);
        if (read == 0) break;

        int written = esp_http_client_write(client, (const char *)buffer, read);
        if (written < 0) {
            ESP_LOGE(TAG, "HTTP write failed");
            err = ESP_FAIL;
            break;
        }
        total_sent += read;
        // ESP_LOGD(TAG, "Sent %d/%ld bytes", total_sent, file_size);
    }

    free(buffer);
    fclose(f);

    if (err == ESP_OK) {
        // 5. Get Response
        int content_length = esp_http_client_fetch_headers(client);
        int status_code = esp_http_client_get_status_code(client);
        
        ESP_LOGI(TAG, "Upload finished. Status: %d, Content-Length: %d", status_code, content_length);

        if (status_code >= 200 && status_code < 300) {
            err = ESP_OK;
        } else {
            ESP_LOGW(TAG, "Upload failed with status %d", status_code);
            err = ESP_FAIL;
        }
    }

    esp_http_client_cleanup(client);
    return err;
}

/**
 * Process upload queue (stub implementation)
 */
esp_err_t upload_process_queue(void) {
    // Implementation would:
    // - Check for pending uploads
    // - Process one item from queue
    // - Handle retry logic
    return ESP_OK;
}

size_t upload_get_queue_length(void) {
    // Return number of pending uploads
    return 0;
}

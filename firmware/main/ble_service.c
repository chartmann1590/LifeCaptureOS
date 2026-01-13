/**
 * BLE GATT Service Implementation (NimBLE)
 *
 * This is a production-quality architecture stub using NimBLE stack.
 * Full implementation would include:
 * - BLE GAP/GATT setup with custom service UUIDs
 * - Command parsing and routing
 * - Session token management
 * - Thumbnail transfer protocol
 *
 * For MVP, this demonstrates the structure.
 */
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_att.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "cJSON.h"

#include "lifecaptureos_config.h"
#include "ble_service.h"
#include "sd_storage.h"
#include "camera_capture.h"
#include "wifi_upload.h"
#include "config_manager.h"
#include "app_state.h"

static const char *TAG = "ble_service";

static bool ble_connected = false;
static uint8_t mac_addr[6];
static uint16_t conn_handle = 0;

static uint16_t rsp_handle;
static uint16_t thm_handle;
static uint8_t cmd_buffer[BLE_MAX_CMD_SIZE + 1];
static size_t cmd_buffer_len = 0;

// Forward declarations
static void ble_app_on_sync(void);
static void ble_app_on_reset(int reason);
static int ble_gap_event(struct ble_gap_event *event, void *arg);
static void handle_ble_command_chunk(const uint8_t *data, size_t len);
static void handle_ble_command_json(cJSON *cmd);
static const char *upload_state_to_string(upload_state_t state);
static void list_media_task(void *param);

typedef struct {
    char request_id[64];
    size_t limit;
    size_t offset;
} list_media_request_t;

// Access callback for characteristics
static int device_access_cb(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg);

// Define GATT services
static const struct ble_gatt_svc_def gatt_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0xFF10),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                // CMD: Write only
                .uuid = BLE_UUID16_DECLARE(0xFF11),
                .access_cb = device_access_cb,
                .flags = BLE_GATT_CHR_F_WRITE,
            },
            {
                // RSP: Notify
                .uuid = BLE_UUID16_DECLARE(0xFF12),
                .access_cb = device_access_cb,
                .flags = BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &rsp_handle,
            },
            {
                // THM: Notify
                .uuid = BLE_UUID16_DECLARE(0xFF13),
                .access_cb = device_access_cb,
                .flags = BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &thm_handle,
            },
            {
                0, /* No more characteristics */
            },
        }
    },
    {
        0, /* No more services */
    },
};

/**
 * Access callback
 */
static int device_access_cb(uint16_t conn_handle, uint16_t attr_handle,
                            struct ble_gatt_access_ctxt *ctxt, void *arg) {
    const ble_uuid_t *uuid = ctxt->chr->uuid;
    char uuid_str[BLE_UUID_STR_LEN];
    ble_uuid_to_str(uuid, uuid_str);
    
    ESP_LOGI(TAG, "GATT access: handle=%d, op=%d, uuid=%s", attr_handle, ctxt->op, uuid_str);

    // Check for CMD write
    if (ble_uuid_u16(uuid) == 0xFF11 && ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint16_t len = OS_MBUF_PKTLEN(ctxt->om);
        if (len > 0) {
            uint8_t *data = malloc(len + 1);
            if (data) {
                int rc = ble_hs_mbuf_to_flat(ctxt->om, data, len, NULL);
                if (rc == 0) {
                    data[len] = 0; // Null terminate
                    handle_ble_command_chunk(data, len);
                }
                free(data);
            }
        }
        return 0;
    }

    return 0;
}

/**
 * BLE host task
 */
static void ble_host_task(void *param) {
    nimble_port_run();
    nimble_port_freertos_deinit();
}

/**
 * Initialize BLE service
 */
esp_err_t ble_service_init(void) {
    ESP_LOGI(TAG, "Initializing BLE service (NimBLE)");

    // Get MAC address for device ID
    esp_read_mac(mac_addr, ESP_MAC_BT);

    // Initialize NimBLE
    esp_err_t ret = nimble_port_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init nimble: %s", esp_err_to_name(ret));
        return ret;
    }

    // Configure the host
    ble_hs_cfg.sync_cb = ble_app_on_sync;
    ble_hs_cfg.reset_cb = ble_app_on_reset;

    // Initialize services
    ble_svc_gap_init();
    ble_svc_gatt_init();

    ble_att_set_preferred_mtu(BLE_MTU_SIZE);

    // Register custom services
    ret = ble_gatts_count_cfg(gatt_svcs);
    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to count services: %d", ret);
        return ESP_FAIL;
    }

    ret = ble_gatts_add_svcs(gatt_svcs);
    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to add services: %d", ret);
        return ESP_FAIL;
    }

    // Set device name
    char device_name[32];
    ble_get_device_id(device_name, sizeof(device_name));
    ble_svc_gap_device_name_set(device_name);

    // Start the task
    nimble_port_freertos_init(ble_host_task);

    ESP_LOGI(TAG, "BLE service initialized");
    return ESP_OK;
}

esp_err_t ble_service_deinit(void) {
    nimble_port_stop();
    nimble_port_deinit();
    return ESP_OK;
}

bool ble_service_is_connected(void) {
    return ble_connected;
}

/**
 * Called when host and controller are synced
 */
static void ble_app_on_sync(void) {
    ESP_LOGI(TAG, "BLE host synced");

    // Make sure we have proper identity address set (public preferred)
    int rc = ble_hs_util_ensure_addr(0);
    if (rc != 0) {
        ESP_LOGE(TAG, "Error ensuring address: %d", rc);
        return;
    }

    // Set advertisement fields
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;

    char device_name[32];
    ble_get_device_id(device_name, sizeof(device_name));
    fields.name = (uint8_t *)device_name;
    fields.name_len = strlen(device_name);
    fields.name_is_complete = 1;
    
    // Advertise our service UUID so Android can filter scan results if needed
    // (though app filters by name too)
    fields.uuids16 = (ble_uuid16_t[]) {
        BLE_UUID16_INIT(0xFF10)
    };
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;

    rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "Error setting adv fields: %d", rc);
        return;
    }

    // Begin advertising
    struct ble_gap_adv_params adv_params = {0};
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    uint8_t own_addr_type;
    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "Error determining address type: %d", rc);
        return;
    }

    rc = ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER,
                           &adv_params, ble_gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "Error starting advertisement: %d", rc);
        return;
    }

    ESP_LOGI(TAG, "BLE advertising started");
}

/**
 * Called when host resets
 */
static void ble_app_on_reset(int reason) {
    ESP_LOGE(TAG, "BLE host reset: %d", reason);
}

/**
 * GAP event handler
 */
static int ble_gap_event(struct ble_gap_event *event, void *arg) {
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        ESP_LOGI(TAG, "BLE connected; status=%d", event->connect.status);
        if (event->connect.status == 0) {
            ble_connected = true;
            conn_handle = event->connect.conn_handle;
            struct ble_gap_upd_params params = {
                .itvl_min = 24,   // 30 ms
                .itvl_max = 40,   // 50 ms
                .latency = 0,
                .supervision_timeout = 3200, // 32 seconds (max)
                .min_ce_len = 0,
                .max_ce_len = 0
            };
            int rc = ble_gap_update_params(conn_handle, &params);
            if (rc != 0) {
                ESP_LOGW(TAG, "Failed to update conn params: %d", rc);
            }
        }
        break;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "BLE disconnected; reason=%d", event->disconnect.reason);
        ble_connected = false;
        conn_handle = 0;
        cmd_buffer_len = 0;

        // Resume advertising
        ble_app_on_sync();
        break;

    case BLE_GAP_EVENT_ADV_COMPLETE:
        ESP_LOGI(TAG, "BLE advertising complete");
        // Restart advertising
        ble_app_on_sync();
        break;

    case BLE_GAP_EVENT_MTU:
        ESP_LOGI(TAG, "BLE MTU update: %d", event->mtu.value);
        break;

    case BLE_GAP_EVENT_SUBSCRIBE:
        ESP_LOGI(TAG, "BLE subscribe event: handle=%d, value=%d", 
                 event->subscribe.attr_handle, event->subscribe.cur_notify);
        break;

    default:
        break;
    }

    return 0;
}

/**
 * Send JSON response over BLE RSP characteristic
 */
esp_err_t ble_send_response(const char *json_response) {
    if (!ble_connected) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!json_response) {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Sending response: %.100s...", json_response);

    size_t len = strlen(json_response);
    bool needs_newline = (len == 0 || json_response[len - 1] != '\n');
    size_t send_len = len + (needs_newline ? 1 : 0);
    size_t max_chunk = BLE_MTU_SIZE - 3;
    const char *payload = json_response;
    char *buffer = NULL;

    if (needs_newline) {
        buffer = (char *)malloc(send_len + 1);
        if (!buffer) {
            return ESP_ERR_NO_MEM;
        }
        memcpy(buffer, json_response, len);
        buffer[len] = '\n';
        buffer[send_len] = '\0';
        payload = buffer;
    }

    size_t offset = 0;
    while (offset < send_len) {
        size_t chunk_len = send_len - offset;
        if (chunk_len > max_chunk) {
            chunk_len = max_chunk;
        }

        struct os_mbuf *om = ble_hs_mbuf_from_flat(payload + offset, chunk_len);
        if (!om) {
            free(buffer);
            return ESP_ERR_NO_MEM;
        }

        int rc = ble_gatts_notify_custom(conn_handle, rsp_handle, om);
        if (rc != 0) {
            ESP_LOGE(TAG, "Notify failed: %d", rc);
            free(buffer);
            return ESP_FAIL;
        }
        offset += chunk_len;
    }

    free(buffer);

    return ESP_OK;
}

/**
 * Send thumbnail chunk over THM characteristic
 */
esp_err_t ble_send_thumbnail_chunk(
    uint32_t transfer_id,
    uint16_t chunk_index,
    const uint8_t *data,
    uint16_t data_len,
    uint32_t crc32
) {
    if (!ble_connected) {
        return ESP_ERR_INVALID_STATE;
    }

    // Build chunk packet:
    // [4B transfer_id][2B chunk_idx][2B size][4B crc32][NB data]
    // Total header: 12 bytes
    
    struct os_mbuf *om = ble_hs_mbuf_from_flat(&transfer_id, 4);
    os_mbuf_append(om, &chunk_index, 2);
    os_mbuf_append(om, &data_len, 2);
    os_mbuf_append(om, &crc32, 4);
    os_mbuf_append(om, data, data_len);

    // Send notification on THM characteristic
    ESP_LOGD(TAG, "Sending thumbnail chunk %u (%u bytes)", chunk_index, data_len);
    
    int rc = ble_gatts_notify_custom(conn_handle, thm_handle, om);
    if (rc != 0) {
        ESP_LOGE(TAG, "Notify failed: %d", rc);
        return ESP_FAIL;
    }

    return ESP_OK;
}

void ble_get_device_id(char *out_id, size_t max_len) {
    snprintf(out_id, max_len, "%s%02x%02x%02x%02x",
             BLE_DEVICE_NAME_PREFIX, mac_addr[2], mac_addr[3], mac_addr[4], mac_addr[5]);
}

/**
 * Command handler (called when CMD characteristic receives data)
 */
static void handle_ble_command_chunk(const uint8_t *data, size_t len) {
    if (len == 0) {
        return;
    }

    if (cmd_buffer_len + len > BLE_MAX_CMD_SIZE) {
        ESP_LOGE(TAG, "BLE command too large, dropping");
        cmd_buffer_len = 0;
        return;
    }

    memcpy(cmd_buffer + cmd_buffer_len, data, len);
    cmd_buffer_len += len;
    cmd_buffer[cmd_buffer_len] = '\0';

    cJSON *cmd = cJSON_Parse((const char *)cmd_buffer);
    if (!cmd) {
        if (cmd_buffer_len >= BLE_MAX_CMD_SIZE ||
            cmd_buffer[cmd_buffer_len - 1] == '}') {
            ESP_LOGE(TAG, "Invalid JSON command");
            cmd_buffer_len = 0;
        }
        return;
    }

    cmd_buffer_len = 0;
    handle_ble_command_json(cmd);
    cJSON_Delete(cmd);
}

static void handle_ble_command_json(cJSON *cmd) {
    cJSON *request_id = cJSON_GetObjectItem(cmd, "request_id");
    if (!request_id) {
        request_id = cJSON_GetObjectItem(cmd, "requestId");
    }
    cJSON *command = cJSON_GetObjectItem(cmd, "command");
    cJSON *params = cJSON_GetObjectItem(cmd, "params");

    if (!request_id || !command) {
        return;
    }

    const char *cmd_str = command->valuestring;
    ESP_LOGI(TAG, "BLE command: %s", cmd_str);

    // Route command
    cJSON *response = cJSON_CreateObject();
    cJSON_AddStringToObject(response, "requestId", request_id->valuestring);

    bool send_response = true;

    if (strcmp(cmd_str, "GET_STATUS") == 0) {
        // Build status response
        cJSON_AddBoolToObject(response, "ok", true);
        cJSON *data = cJSON_AddObjectToObject(response, "data");

        device_config_t cfg;
        lifecaptureos_config_load(&cfg);

        cJSON_AddStringToObject(data, "firmwareVersion", FIRMWARE_VERSION);

        char device_id[32];
        ble_get_device_id(device_id, sizeof(device_id));
        cJSON_AddStringToObject(data, "deviceId", device_id);

        cJSON_AddStringToObject(data, "mode", app_is_capture_active() ? "capturing" : "idle");

        // Add required fields to prevent app crash
        cJSON *sd = cJSON_AddObjectToObject(data, "sdCard");
        uint64_t total = 0;
        uint64_t free = 0;
        uint64_t used = 0;
        if (sd_get_storage_info(&total, &free, &used) != ESP_OK) {
            total = 0;
            free = 0;
            used = 0;
        }
        cJSON_AddBoolToObject(sd, "mounted", sd_storage_is_mounted());
        cJSON_AddNumberToObject(sd, "totalMb", (double)(total / (1024 * 1024)));
        cJSON_AddNumberToObject(sd, "freeMb", (double)(free / (1024 * 1024)));
        cJSON_AddNumberToObject(sd, "usedMb", (double)(used / (1024 * 1024)));

        cJSON *storage = cJSON_AddObjectToObject(data, "storage");
        cJSON_AddBoolToObject(storage, "auto_delete_24h", cfg.auto_delete_24h);

        cJSON *wifi = cJSON_AddObjectToObject(data, "wifi");
        cJSON_AddBoolToObject(wifi, "connected", wifi_is_connected());
        cJSON_AddStringToObject(wifi, "ssid", cfg.wifi_ssid);
        cJSON_AddNumberToObject(wifi, "rssi", 0);
        cJSON_AddStringToObject(wifi, "ip", "");

        cJSON *capture = cJSON_AddObjectToObject(data, "capture");
        cJSON_AddNumberToObject(capture, "totalCount", (double)sd_get_media_count());
        cJSON_AddNumberToObject(capture, "todayCount", 0);
        cJSON_AddNumberToObject(capture, "lastCaptureTimestamp", (double)app_get_last_capture_timestamp());
        cJSON_AddNumberToObject(capture, "intervalSeconds", (double)cfg.capture_interval_sec);
        cJSON_AddNumberToObject(capture, "quality", (double)cfg.jpeg_quality);
        cJSON_AddStringToObject(capture, "resolution", "1600x1200");

        cJSON *upload = cJSON_AddObjectToObject(data, "upload");
        cJSON_AddNumberToObject(upload, "queueLength", (double)upload_get_queue_length());
        cJSON_AddBoolToObject(upload, "uploading", false);
        cJSON_AddNumberToObject(upload, "lastUploadTimestamp", 0);
        cJSON_AddNumberToObject(upload, "failedCount", 0);

    } else if (strcmp(cmd_str, "GET_CAPTURE_STATS") == 0) {
        cJSON_AddBoolToObject(response, "ok", true);
        cJSON *data = cJSON_AddObjectToObject(response, "data");
        cJSON_AddNumberToObject(data, "attempts", (double)app_get_capture_attempts());
        cJSON_AddNumberToObject(data, "successes", (double)app_get_capture_successes());
        cJSON_AddNumberToObject(data, "failures", (double)app_get_capture_failures());
        cJSON_AddNumberToObject(data, "timerTicks", (double)app_get_capture_timer_ticks());
        cJSON_AddNumberToObject(data, "lastCaptureTimestamp", (double)app_get_last_capture_timestamp());
        const char *last_error = app_get_last_capture_error();
        if (last_error && strlen(last_error) > 0) {
            cJSON_AddStringToObject(data, "lastError", last_error);
        } else {
            cJSON_AddNullToObject(data, "lastError");
        }

    } else if (strcmp(cmd_str, "LIST_MEDIA") == 0) {
        if (!sd_storage_is_mounted()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "SD_NOT_MOUNTED");
            cJSON_AddStringToObject(error, "message", "SD card not mounted");
            cJSON_AddObjectToObject(response, "data");
        } else {
            size_t limit = 50;
            size_t offset = 0;

            if (params) {
                cJSON *limit_param = cJSON_GetObjectItem(params, "limit");
                cJSON *offset_param = cJSON_GetObjectItem(params, "offset");
                if (limit_param && cJSON_IsNumber(limit_param)) {
                    int value = limit_param->valueint;
                    if (value >= 0) {
                        limit = (size_t)value;
                    }
                }
                if (offset_param && cJSON_IsNumber(offset_param)) {
                    int value = offset_param->valueint;
                    if (value >= 0) {
                        offset = (size_t)value;
                    }
                }
            }

            if (limit == 0) {
                limit = 1;
            }
            if (limit > 1) {
                limit = 1;
            }

            list_media_request_t *req = calloc(1, sizeof(list_media_request_t));
            if (!req) {
                cJSON_AddBoolToObject(response, "ok", false);
                cJSON *error = cJSON_AddObjectToObject(response, "error");
                cJSON_AddStringToObject(error, "code", "NO_MEM");
                cJSON_AddStringToObject(error, "message", "Out of memory");
                cJSON_AddObjectToObject(response, "data");
            } else {
                strncpy(req->request_id, request_id->valuestring, sizeof(req->request_id) - 1);
                req->limit = limit;
                req->offset = offset;
                if (xTaskCreate(list_media_task, "ble_list_media", 6144, req, 5, NULL) != pdPASS) {
                    free(req);
                    cJSON_AddBoolToObject(response, "ok", false);
                    cJSON *error = cJSON_AddObjectToObject(response, "error");
                    cJSON_AddStringToObject(error, "code", "TASK_FAILED");
                    cJSON_AddStringToObject(error, "message", "Failed to queue list task");
                    cJSON_AddObjectToObject(response, "data");
                } else {
                    send_response = false;
                }
            }
        }
    } else if (strcmp(cmd_str, "START_STORY") == 0) {
        if (!sd_storage_is_mounted()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "SD_NOT_MOUNTED");
            cJSON_AddStringToObject(error, "message", "SD card not mounted");
            cJSON_AddObjectToObject(response, "data");
        } else if (!camera_is_initialized()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "CAMERA_NOT_READY");
            cJSON_AddStringToObject(error, "message", "Camera not initialized");
            cJSON_AddObjectToObject(response, "data");
        } else if (app_is_capture_active()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "ALREADY_CAPTURING");
            cJSON_AddStringToObject(error, "message", "Capture already active");
            cJSON_AddObjectToObject(response, "data");
        } else {
            start_capture();
            cJSON_AddBoolToObject(response, "ok", true);
            cJSON *data = cJSON_AddObjectToObject(response, "data");
            cJSON_AddStringToObject(data, "mode", "capturing");
        }
    } else if (strcmp(cmd_str, "STOP_STORY") == 0) {
        if (!app_is_capture_active()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "NOT_CAPTURING");
            cJSON_AddStringToObject(error, "message", "Capture not active");
            cJSON_AddObjectToObject(response, "data");
        } else {
            stop_capture();
            cJSON_AddBoolToObject(response, "ok", true);
            cJSON *data = cJSON_AddObjectToObject(response, "data");
            cJSON_AddStringToObject(data, "mode", "idle");
        }
    } else if (strcmp(cmd_str, "AUTH") == 0) {
        // Mock Auth
        cJSON_AddBoolToObject(response, "ok", true);
        cJSON *data = cJSON_AddObjectToObject(response, "data");
        cJSON_AddStringToObject(data, "session_token", "mock_session_token_123");
    } else if (strcmp(cmd_str, "WIFI_PROVISION") == 0) {
        device_config_t cfg;
        lifecaptureos_config_load(&cfg);

        if (params) {
            cJSON *ssid = cJSON_GetObjectItem(params, "ssid");
            cJSON *password = cJSON_GetObjectItem(params, "password");
            if (ssid && cJSON_IsString(ssid)) {
                ESP_LOGI(TAG, "Provisioning WiFi: %s", ssid->valuestring);
                strncpy(cfg.wifi_ssid, ssid->valuestring, sizeof(cfg.wifi_ssid) - 1);
                cfg.wifi_ssid[sizeof(cfg.wifi_ssid) - 1] = '\0';
            }
            if (password && cJSON_IsString(password)) {
                strncpy(cfg.wifi_password, password->valuestring, sizeof(cfg.wifi_password) - 1);
                cfg.wifi_password[sizeof(cfg.wifi_password) - 1] = '\0';
            }
        }

        lifecaptureos_config_save(&cfg);
        app_apply_config(&cfg);
        if (strlen(cfg.wifi_ssid) > 0) {
            wifi_connect(cfg.wifi_ssid, cfg.wifi_password);
        }

        cJSON_AddBoolToObject(response, "ok", true);
        cJSON_AddObjectToObject(response, "data");
    } else if (strcmp(cmd_str, "SET_BACKEND") == 0) {
        device_config_t cfg;
        lifecaptureos_config_load(&cfg);

        if (params) {
            cJSON *backend_url = cJSON_GetObjectItem(params, "backend_url");
            cJSON *device_token = cJSON_GetObjectItem(params, "device_token");
            cJSON *device_id_param = cJSON_GetObjectItem(params, "device_id");

            if (backend_url && cJSON_IsString(backend_url)) {
                strncpy(cfg.backend_url, backend_url->valuestring, sizeof(cfg.backend_url) - 1);
                cfg.backend_url[sizeof(cfg.backend_url) - 1] = '\0';
            }

            if (device_token && cJSON_IsString(device_token)) {
                strncpy(cfg.device_token, device_token->valuestring, sizeof(cfg.device_token) - 1);
                cfg.device_token[sizeof(cfg.device_token) - 1] = '\0';
            }

            if (device_id_param && cJSON_IsString(device_id_param)) {
                strncpy(cfg.device_id, device_id_param->valuestring, sizeof(cfg.device_id) - 1);
                cfg.device_id[sizeof(cfg.device_id) - 1] = '\0';
            } else {
                ble_get_device_id(cfg.device_id, sizeof(cfg.device_id));
            }
        } else {
            ble_get_device_id(cfg.device_id, sizeof(cfg.device_id));
        }

        lifecaptureos_config_save(&cfg);
        app_apply_config(&cfg);
        if (strlen(cfg.backend_url) > 0 && strlen(cfg.device_token) > 0) {
            upload_init(cfg.backend_url, cfg.device_token, cfg.device_id);
        }

        cJSON_AddBoolToObject(response, "ok", true);
        cJSON *data = cJSON_AddObjectToObject(response, "data");
        cJSON_AddStringToObject(data, "device_id", cfg.device_id);
    } else if (strcmp(cmd_str, "SET_CONFIG") == 0) {
        device_config_t cfg;
        lifecaptureos_config_load(&cfg);

        bool has_update = false;
        bool invalid = false;
        cJSON *updated = cJSON_CreateArray();

        if (params) {
            cJSON *capture = cJSON_GetObjectItem(params, "capture");
            cJSON *upload = cJSON_GetObjectItem(params, "upload");
            cJSON *storage = cJSON_GetObjectItem(params, "storage");

            if (capture && cJSON_IsObject(capture)) {
                cJSON *interval = cJSON_GetObjectItem(capture, "interval_seconds");
                if (!interval) {
                    interval = cJSON_GetObjectItem(capture, "intervalSeconds");
                }
                if (interval && cJSON_IsNumber(interval)) {
                    int value = interval->valueint;
                    if (value < MIN_CAPTURE_INTERVAL_SEC || value > MAX_CAPTURE_INTERVAL_SEC) {
                        invalid = true;
                    } else {
                        cfg.capture_interval_sec = (uint16_t)value;
                        cJSON_AddItemToArray(updated, cJSON_CreateString("capture.interval_seconds"));
                        has_update = true;
                    }
                }

                cJSON *quality = cJSON_GetObjectItem(capture, "quality");
                if (quality && cJSON_IsNumber(quality)) {
                    int value = quality->valueint;
                    if (value < MIN_JPEG_QUALITY || value > MAX_JPEG_QUALITY) {
                        invalid = true;
                    } else {
                        cfg.jpeg_quality = (uint8_t)value;
                        cJSON_AddItemToArray(updated, cJSON_CreateString("capture.quality"));
                        has_update = true;
                    }
                }
            }

            if (upload && cJSON_IsObject(upload)) {
                cJSON *auto_upload = cJSON_GetObjectItem(upload, "auto_upload");
                if (!auto_upload) {
                    auto_upload = cJSON_GetObjectItem(upload, "autoUpload");
                }
                if (auto_upload && cJSON_IsBool(auto_upload)) {
                    cfg.auto_upload = cJSON_IsTrue(auto_upload);
                    cJSON_AddItemToArray(updated, cJSON_CreateString("upload.auto_upload"));
                    has_update = true;
                }
            }

            if (storage && cJSON_IsObject(storage)) {
                cJSON *auto_delete = cJSON_GetObjectItem(storage, "auto_delete_24h");
                if (!auto_delete) {
                    auto_delete = cJSON_GetObjectItem(storage, "autoDelete24h");
                }
                if (auto_delete && cJSON_IsBool(auto_delete)) {
                    cfg.auto_delete_24h = cJSON_IsTrue(auto_delete);
                    cJSON_AddItemToArray(updated, cJSON_CreateString("storage.auto_delete_24h"));
                    has_update = true;
                }
            }
        }

        if (!has_update || invalid) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", invalid ? "VALUE_OUT_OF_RANGE" : "INVALID_PARAMS");
            cJSON_AddStringToObject(error, "message", invalid ? "One or more values are out of range" : "No valid settings provided");
            cJSON_AddObjectToObject(response, "data");
            cJSON_Delete(updated);
        } else {
            lifecaptureos_config_save(&cfg);
            app_apply_config(&cfg);
            cJSON_AddBoolToObject(response, "ok", true);
            cJSON *data = cJSON_AddObjectToObject(response, "data");
            cJSON_AddItemToObject(data, "updated", updated);
            cJSON_AddBoolToObject(data, "rebootRequired", false);
        }
    } else if (strcmp(cmd_str, "CLEAR_STORAGE") == 0) {
        if (!sd_storage_is_mounted()) {
            cJSON_AddBoolToObject(response, "ok", false);
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "SD_NOT_MOUNTED");
            cJSON_AddStringToObject(error, "message", "SD card not mounted");
            cJSON_AddObjectToObject(response, "data");
        } else {
            const char *confirm_value = NULL;
            if (params) {
                cJSON *confirm = cJSON_GetObjectItem(params, "confirm");
                if (confirm && cJSON_IsString(confirm)) {
                    confirm_value = confirm->valuestring;
                }
            }

            if (!confirm_value || strcmp(confirm_value, "CLEAR_ALL") != 0) {
                cJSON_AddBoolToObject(response, "ok", false);
                cJSON *error = cJSON_AddObjectToObject(response, "error");
                cJSON_AddStringToObject(error, "code", "CONFIRMATION_REQUIRED");
                cJSON_AddStringToObject(error, "message", "Missing confirmation");
                cJSON_AddObjectToObject(response, "data");
            } else {
                size_t deleted = 0;
                uint64_t freed = 0;
                esp_err_t err = sd_clear_storage(&deleted, &freed);
                if (err != ESP_OK) {
                    cJSON_AddBoolToObject(response, "ok", false);
                    cJSON *error = cJSON_AddObjectToObject(response, "error");
                    cJSON_AddStringToObject(error, "code", "DEVICE_ERROR");
                    cJSON_AddStringToObject(error, "message", "Failed to clear storage");
                    cJSON_AddObjectToObject(response, "data");
                } else {
                    cJSON_AddBoolToObject(response, "ok", true);
                    cJSON *data = cJSON_AddObjectToObject(response, "data");
                    cJSON_AddBoolToObject(data, "cleared", true);
                    cJSON_AddNumberToObject(data, "files_deleted", (double)deleted);
                    cJSON_AddNumberToObject(data, "freed_bytes", (double)freed);
                }
            }
        }
    } else {
        cJSON_AddBoolToObject(response, "ok", false);
        cJSON *error = cJSON_AddObjectToObject(response, "error");
        cJSON_AddStringToObject(error, "code", "UNKNOWN_COMMAND");
        cJSON_AddStringToObject(error, "message", "Unknown command");
        cJSON_AddObjectToObject(response, "data");  // Empty data object required by Android
    }

    if (send_response) {
        // Send response
        char *response_str = cJSON_PrintUnformatted(response);
        ble_send_response(response_str);
        free(response_str);
    }

    cJSON_Delete(response);
}

static const char *upload_state_to_string(upload_state_t state) {
    switch (state) {
    case UPLOAD_STATE_PENDING:
        return "pending";
    case UPLOAD_STATE_UPLOADING:
        return "uploading";
    case UPLOAD_STATE_COMPLETED:
        return "completed";
    case UPLOAD_STATE_FAILED:
        return "failed";
    default:
        return "pending";
    }
}

static void list_media_task(void *param) {
    list_media_request_t *req = (list_media_request_t *)param;
    if (!req) {
        vTaskDelete(NULL);
        return;
    }

    cJSON *response = cJSON_CreateObject();
    cJSON_AddStringToObject(response, "requestId", req->request_id);
    cJSON_AddBoolToObject(response, "ok", true);

    cJSON *data = cJSON_AddObjectToObject(response, "data");
    cJSON *items = cJSON_AddArrayToObject(data, "items");

    size_t total = 0;
    size_t count = 0;

    media_metadata_t *list = calloc(req->limit, sizeof(media_metadata_t));
    if (!list) {
        cJSON_ReplaceItemInObject(response, "ok", cJSON_CreateBool(false));
        cJSON *error = cJSON_AddObjectToObject(response, "error");
        cJSON_AddStringToObject(error, "code", "NO_MEM");
        cJSON_AddStringToObject(error, "message", "Out of memory");
    } else {
        esp_err_t err = sd_list_media(list, req->limit, req->offset, &count, &total);
        if (err != ESP_OK) {
            cJSON_ReplaceItemInObject(response, "ok", cJSON_CreateBool(false));
            cJSON *error = cJSON_AddObjectToObject(response, "error");
            cJSON_AddStringToObject(error, "code", "LIST_FAILED");
            cJSON_AddStringToObject(error, "message", "Failed to list media");
        } else {
            for (size_t i = 0; i < count; i++) {
                media_metadata_t *meta = &list[i];
                cJSON *item = cJSON_CreateObject();
                cJSON_AddStringToObject(item, "id", meta->media_id);
                cJSON_AddStringToObject(item, "type",
                                        meta->type == MEDIA_TYPE_VIDEO ? "video" : "image");
                cJSON_AddNumberToObject(item, "capturedAt", (double)meta->captured_at);
                cJSON_AddStringToObject(item, "filename", meta->filename);
                cJSON_AddNullToObject(item, "thumbnail");
                cJSON_AddNumberToObject(item, "sizeBytes", (double)meta->size_bytes);
                cJSON_AddNumberToObject(item, "thumbSizeBytes",
                                        (double)meta->thumb_size_bytes);
                if (strlen(meta->resolution) > 0) {
                    cJSON_AddStringToObject(item, "resolution", meta->resolution);
                } else {
                    cJSON_AddStringToObject(item, "resolution", "1600x1200");
                }
                cJSON_AddStringToObject(item, "uploadState",
                                        upload_state_to_string(meta->upload_state));
                cJSON_AddNumberToObject(item, "uploadProgress",
                                        meta->upload_state == UPLOAD_STATE_COMPLETED ? 1.0 : 0.0);
                cJSON_AddItemToArray(items, item);
            }
        }
        free(list);
    }

    cJSON_AddNumberToObject(data, "total", (double)total);
    cJSON_AddNumberToObject(data, "offset", (double)req->offset);
    cJSON_AddNumberToObject(data, "limit", (double)req->limit);

    char *response_str = cJSON_PrintUnformatted(response);
    ble_send_response(response_str);
    free(response_str);
    cJSON_Delete(response);
    free(req);

    vTaskDelete(NULL);
}

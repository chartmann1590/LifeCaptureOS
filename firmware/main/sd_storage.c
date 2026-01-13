/**
 * SD Card Storage Implementation
 */
#include <string.h>
#include <stdio.h>
#include <sys/stat.h>
#include <dirent.h>
#include <errno.h>
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "driver/sdmmc_host.h"
#include "driver/sdspi_host.h"
#include "sdmmc_cmd.h"
#include "cJSON.h"

#include "lifecaptureos_config.h"
#include "sd_storage.h"

static const char *TAG = "sd_storage";

static bool is_mounted = false;
static sdmmc_card_t *card = NULL;
static size_t media_count_cache = 0;
static char sd_last_error[64] = {0};

static void set_sd_error(const char *code) {
    if (!code) {
        sd_last_error[0] = '\0';
        return;
    }
    strncpy(sd_last_error, code, sizeof(sd_last_error) - 1);
    sd_last_error[sizeof(sd_last_error) - 1] = '\0';
}

static size_t count_index_lines(void) {
    FILE *f = fopen(DCIM_INDEX_FILE, "r");
    if (!f) {
        return 0;
    }

    size_t count = 0;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        count++;
    }

    fclose(f);
    return count;
}

static esp_err_t load_metadata_from_path(const char *media_id, time_t timestamp, media_metadata_t *out_metadata);

static bool join_path(char *out, size_t out_len, const char *dir, const char *file) {
    if (!out || !dir || !file || out_len == 0) {
        return false;
    }

    size_t dir_len = strnlen(dir, out_len);
    size_t file_len = strnlen(file, out_len);
    if (dir_len == out_len || file_len == out_len) {
        return false;
    }

    if (dir_len + 1 + file_len + 1 > out_len) {
        return false;
    }

    memcpy(out, dir, dir_len);
    out[dir_len] = '/';
    memcpy(out + dir_len + 1, file, file_len);
    out[dir_len + 1 + file_len] = '\0';
    return true;
}

static uint64_t get_file_size(const char *path) {
    if (!path || path[0] == '\0') {
        return 0;
    }

    struct stat st;
    if (stat(path, &st) != 0) {
        return 0;
    }

    return (uint64_t)st.st_size;
}

static void delete_media_files(const media_metadata_t *meta, uint64_t *freed_bytes) {
    if (!meta) {
        return;
    }

    uint64_t freed = freed_bytes ? *freed_bytes : 0;

    if (meta->full_path[0] != '\0') {
        freed += get_file_size(meta->full_path);
        if (remove(meta->full_path) != 0 && errno != ENOENT) {
            ESP_LOGW(TAG, "Failed to remove media file: %s", meta->full_path);
        }
    }

    if (meta->thumb_path[0] != '\0') {
        freed += get_file_size(meta->thumb_path);
        if (remove(meta->thumb_path) != 0 && errno != ENOENT) {
            ESP_LOGW(TAG, "Failed to remove thumbnail: %s", meta->thumb_path);
        }
    }

    if (meta->meta_path[0] != '\0') {
        freed += get_file_size(meta->meta_path);
        if (remove(meta->meta_path) != 0 && errno != ENOENT) {
            ESP_LOGW(TAG, "Failed to remove metadata: %s", meta->meta_path);
        }
    }

    if (freed_bytes) {
        *freed_bytes = freed;
    }
}

typedef bool (*index_delete_fn)(const char *media_id, time_t timestamp, void *ctx);

static esp_err_t prune_index_entries(
    index_delete_fn should_delete,
    void *ctx,
    size_t *out_deleted,
    uint64_t *out_freed_bytes
) {
    if (!is_mounted) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!should_delete) {
        return ESP_ERR_INVALID_ARG;
    }

    FILE *f = fopen(DCIM_INDEX_FILE, "r");
    if (!f) {
        if (out_deleted) {
            *out_deleted = 0;
        }
        if (out_freed_bytes) {
            *out_freed_bytes = 0;
        }
        media_count_cache = 0;
        return ESP_OK;
    }

    char temp_path[MAX_PATH_LEN];
    snprintf(temp_path, sizeof(temp_path), "%s/index.tmp", DCIM_BASE_PATH);
    FILE *out = fopen(temp_path, "w");
    if (!out) {
        fclose(f);
        return ESP_FAIL;
    }

    size_t kept = 0;
    size_t removed = 0;
    uint64_t freed_total = 0;
    char line[256];

    while (fgets(line, sizeof(line), f)) {
        cJSON *entry = cJSON_Parse(line);
        if (!entry) {
            fputs(line, out);
            kept++;
            continue;
        }

        cJSON *id = cJSON_GetObjectItem(entry, "media_id");
        cJSON *ts = cJSON_GetObjectItem(entry, "timestamp");
        bool delete_entry = false;

        if (id && cJSON_IsString(id) && ts && cJSON_IsNumber(ts)) {
            delete_entry = should_delete(id->valuestring, (time_t)ts->valuedouble, ctx);
        }

        if (delete_entry) {
            media_metadata_t meta;
            if (load_metadata_from_path(id->valuestring, (time_t)ts->valuedouble, &meta) == ESP_OK) {
                delete_media_files(&meta, &freed_total);
            }
            removed++;
        } else {
            fputs(line, out);
            kept++;
        }

        cJSON_Delete(entry);
    }

    fclose(f);
    fclose(out);

    if (rename(temp_path, DCIM_INDEX_FILE) != 0) {
        if (remove(DCIM_INDEX_FILE) != 0 && errno != ENOENT) {
            ESP_LOGE(TAG, "Failed to replace index file");
            return ESP_FAIL;
        }
        if (rename(temp_path, DCIM_INDEX_FILE) != 0) {
            ESP_LOGE(TAG, "Failed to replace index file");
            return ESP_FAIL;
        }
    }

    media_count_cache = kept;

    if (out_deleted) {
        *out_deleted = removed;
    }
    if (out_freed_bytes) {
        *out_freed_bytes = freed_total;
    }

    return ESP_OK;
}

static esp_err_t read_file_to_buffer(const char *path, uint8_t **out_data, size_t *out_len) {
    if (!out_data || !out_len) {
        return ESP_ERR_INVALID_ARG;
    }

    FILE *f = fopen(path, "rb");
    if (!f) {
        return ESP_FAIL;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    if (size <= 0) {
        fclose(f);
        return ESP_FAIL;
    }
    fseek(f, 0, SEEK_SET);

    uint8_t *buffer = (uint8_t *)malloc((size_t)size);
    if (!buffer) {
        fclose(f);
        return ESP_ERR_NO_MEM;
    }

    size_t read = fread(buffer, 1, (size_t)size, f);
    fclose(f);

    if (read != (size_t)size) {
        free(buffer);
        return ESP_FAIL;
    }

    *out_data = buffer;
    *out_len = (size_t)size;
    return ESP_OK;
}

/**
 * Initialize SD card and mount filesystem
 */
esp_err_t sd_storage_init(void) {
    if (is_mounted) {
        ESP_LOGW(TAG, "SD card already mounted");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Initializing SD card using SDMMC 1-bit mode");

    // Host Config
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.flags = SDMMC_HOST_FLAG_1BIT;
    host.max_freq_khz = SDMMC_FREQ_DEFAULT;

    // Slot Config
    sdmmc_slot_config_t slot_config = SDMMC_SLOT_CONFIG_DEFAULT();
    slot_config.width = 1;
    slot_config.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    // Mount Config
    esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = true, // Enable formatting
        .max_files = SD_MAX_FILES,
        .allocation_unit_size = 16 * 1024
    };

    // Mount filesystem using SDMMC
    esp_err_t ret = esp_vfs_fat_sdmmc_mount(
        SD_MOUNT_POINT,
        &host,
        &slot_config,
        &mount_config,
        &card
    );

    if (ret != ESP_OK) {
        if (ret == ESP_FAIL) {
            ESP_LOGE(TAG, "Failed to mount filesystem");
        } else {
            ESP_LOGE(TAG, "Failed to initialize SD card: %s", esp_err_to_name(ret));
        }
        return ret;
    }

    is_mounted = true;

    // Create DCIM directory structure
    struct stat st;
    if (stat(DCIM_BASE_PATH, &st) != 0) {
        ESP_LOGI(TAG, "Creating DCIM directory structure");
        mkdir(SD_MOUNT_POINT "/DCIM", 0775);
        mkdir(DCIM_BASE_PATH, 0775);
    }

    // Log card info
    ESP_LOGI(TAG, "SD card mounted successfully");
    ESP_LOGI(TAG, "Card name: %s", card->cid.name);
    ESP_LOGI(TAG, "Card size: %llu MB", ((uint64_t) card->csd.capacity) * card->csd.sector_size / (1024 * 1024));

    media_count_cache = count_index_lines();
    set_sd_error(NULL);

    return ESP_OK;
}

/**
 * Unmount SD card
 */
esp_err_t sd_storage_deinit(void) {
    if (!is_mounted) {
        return ESP_OK;
    }

    esp_err_t ret = esp_vfs_fat_sdcard_unmount(SD_MOUNT_POINT, card);
    if (ret == ESP_OK) {
        is_mounted = false;
        ESP_LOGI(TAG, "SD card unmounted");
    }

    return ret;
}

bool sd_storage_is_mounted(void) {
    return is_mounted;
}

/**
 * Generate media ID: IMG_<timestamp>_<counter> or VID_<timestamp>_<counter>
 */
static void generate_media_id(media_type_t type, time_t timestamp, char *out_id, size_t max_len) {
    static uint32_t counter = 0;
    const char *prefix = (type == MEDIA_TYPE_IMAGE) ? "IMG" : "VID";
    snprintf(out_id, max_len, "%s_%ld_%04lu", prefix, (long)timestamp, (unsigned long)counter++);
}

/**
 * Get date path: YYYY/MM/DD
 */
static void get_date_path(time_t timestamp, char *out_path, size_t max_len) {
    struct tm timeinfo;
    localtime_r(&timestamp, &timeinfo);
    snprintf(out_path, max_len, "%04d/%02d/%02d",
             timeinfo.tm_year + 1900,
             timeinfo.tm_mon + 1,
             timeinfo.tm_mday);
}

static bool find_index_entry(const char *media_id, time_t *out_timestamp, media_type_t *out_type) {
    if (!media_id || !is_mounted) {
        return false;
    }

    FILE *f = fopen(DCIM_INDEX_FILE, "r");
    if (!f) {
        return false;
    }

    bool found = false;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        cJSON *entry = cJSON_Parse(line);
        if (!entry) {
            continue;
        }

        cJSON *id = cJSON_GetObjectItem(entry, "media_id");
        if (id && cJSON_IsString(id) && strcmp(id->valuestring, media_id) == 0) {
            cJSON *ts = cJSON_GetObjectItem(entry, "timestamp");
            cJSON *type = cJSON_GetObjectItem(entry, "type");
            if (ts && cJSON_IsNumber(ts)) {
                if (out_timestamp) {
                    *out_timestamp = (time_t)ts->valuedouble;
                }
            }
            if (type && cJSON_IsNumber(type)) {
                if (out_type) {
                    *out_type = (media_type_t)type->valueint;
                }
            }
            found = true;
            cJSON_Delete(entry);
            break;
        }

        cJSON_Delete(entry);
    }

    fclose(f);
    return found;
}

static esp_err_t load_metadata_from_path(const char *media_id, time_t timestamp, media_metadata_t *out_metadata) {
    if (!out_metadata || !media_id) {
        return ESP_ERR_INVALID_ARG;
    }

    memset(out_metadata, 0, sizeof(*out_metadata));
    strncpy(out_metadata->media_id, media_id, MAX_MEDIA_ID_LEN);
    out_metadata->captured_at = timestamp;

    char date_path[64];
    char dir_path[MAX_PATH_LEN];
    get_date_path(timestamp, date_path, sizeof(date_path));
    snprintf(dir_path, sizeof(dir_path), "%s/%s", DCIM_BASE_PATH, date_path);

    snprintf(out_metadata->filename, sizeof(out_metadata->filename), "%s.jpg", media_id);
    snprintf(out_metadata->thumb_filename, sizeof(out_metadata->thumb_filename), "THM_%s.jpg", media_id);
    snprintf(out_metadata->meta_filename, sizeof(out_metadata->meta_filename), "META_%s.json", media_id);

    if (!join_path(out_metadata->full_path, sizeof(out_metadata->full_path), dir_path, out_metadata->filename)) {
        out_metadata->full_path[0] = '\0';
    }
    if (!join_path(out_metadata->thumb_path, sizeof(out_metadata->thumb_path), dir_path, out_metadata->thumb_filename)) {
        out_metadata->thumb_path[0] = '\0';
    }
    if (!join_path(out_metadata->meta_path, sizeof(out_metadata->meta_path), dir_path, out_metadata->meta_filename)) {
        out_metadata->meta_path[0] = '\0';
    }

    uint8_t *meta_buf = NULL;
    size_t meta_len = 0;
    if (read_file_to_buffer(out_metadata->meta_path, &meta_buf, &meta_len) != ESP_OK) {
        return ESP_OK;
    }

    char *meta_str = (char *)malloc(meta_len + 1);
    if (!meta_str) {
        free(meta_buf);
        return ESP_ERR_NO_MEM;
    }
    memcpy(meta_str, meta_buf, meta_len);
    meta_str[meta_len] = '\0';
    free(meta_buf);

    cJSON *meta = cJSON_Parse(meta_str);
    free(meta_str);
    if (!meta) {
        return ESP_OK;
    }

    cJSON *filename = cJSON_GetObjectItem(meta, "filename");
    if (filename && cJSON_IsString(filename)) {
        strncpy(out_metadata->filename, filename->valuestring, sizeof(out_metadata->filename));
        if (!join_path(out_metadata->full_path, sizeof(out_metadata->full_path), dir_path, out_metadata->filename)) {
            out_metadata->full_path[0] = '\0';
        }
    }

    cJSON *thumb_filename = cJSON_GetObjectItem(meta, "thumb_filename");
    if (thumb_filename && cJSON_IsString(thumb_filename)) {
        strncpy(out_metadata->thumb_filename, thumb_filename->valuestring, sizeof(out_metadata->thumb_filename));
        if (!join_path(out_metadata->thumb_path, sizeof(out_metadata->thumb_path), dir_path, out_metadata->thumb_filename)) {
            out_metadata->thumb_path[0] = '\0';
        }
    }

    cJSON *size_bytes = cJSON_GetObjectItem(meta, "size_bytes");
    if (size_bytes && cJSON_IsNumber(size_bytes)) {
        out_metadata->size_bytes = (uint32_t)size_bytes->valueint;
    }

    cJSON *thumb_size_bytes = cJSON_GetObjectItem(meta, "thumb_size_bytes");
    if (thumb_size_bytes && cJSON_IsNumber(thumb_size_bytes)) {
        out_metadata->thumb_size_bytes = (uint32_t)thumb_size_bytes->valueint;
    }

    cJSON *resolution = cJSON_GetObjectItem(meta, "resolution");
    if (resolution && cJSON_IsString(resolution)) {
        strncpy(out_metadata->resolution, resolution->valuestring, sizeof(out_metadata->resolution));
    }

    cJSON *quality = cJSON_GetObjectItem(meta, "quality");
    if (quality && cJSON_IsNumber(quality)) {
        out_metadata->quality = (uint8_t)quality->valueint;
    }

    cJSON *upload_state = cJSON_GetObjectItem(meta, "upload_state");
    if (upload_state && cJSON_IsNumber(upload_state)) {
        out_metadata->upload_state = (upload_state_t)upload_state->valueint;
    }

    cJSON_Delete(meta);
    return ESP_OK;
}

/**
 * Create media entry: save media file, thumbnail, and metadata
 */
esp_err_t sd_create_media_entry(
    media_type_t type,
    time_t timestamp,
    const uint8_t *data,
    size_t data_len,
    const uint8_t *thumbnail,
    size_t thumb_len,
    uint8_t quality,
    const char *resolution,
    media_metadata_t *out_metadata
) {
    if (!is_mounted) {
        ESP_LOGE(TAG, "SD card not mounted");
        set_sd_error("NOT_MOUNTED");
        return ESP_ERR_INVALID_STATE;
    }
    set_sd_error(NULL);

    // Generate media ID and paths
    char media_id[MAX_MEDIA_ID_LEN];
    char date_path[64];
    char dir_path[MAX_PATH_LEN];

    generate_media_id(type, timestamp, media_id, sizeof(media_id));
    get_date_path(timestamp, date_path, sizeof(date_path));
    snprintf(dir_path, sizeof(dir_path), "%s/%s", DCIM_BASE_PATH, date_path);

    // Create directory structure
    char temp_path[MAX_PATH_LEN];
    snprintf(temp_path, sizeof(temp_path), "%s/%04d", DCIM_BASE_PATH,
             ((struct tm *)localtime(&timestamp))->tm_year + 1900);
    if (mkdir(temp_path, 0775) != 0 && errno != EEXIST) {
        ESP_LOGE(TAG, "Failed to create year dir: %s", temp_path);
        set_sd_error("MKDIR_YEAR");
        return ESP_FAIL;
    }

    snprintf(temp_path, sizeof(temp_path), "%s/%04d/%02d", DCIM_BASE_PATH,
             ((struct tm *)localtime(&timestamp))->tm_year + 1900,
             ((struct tm *)localtime(&timestamp))->tm_mon + 1);
    if (mkdir(temp_path, 0775) != 0 && errno != EEXIST) {
        ESP_LOGE(TAG, "Failed to create month dir: %s", temp_path);
        set_sd_error("MKDIR_MONTH");
        return ESP_FAIL;
    }

    if (mkdir(dir_path, 0775) != 0 && errno != EEXIST) {
        ESP_LOGE(TAG, "Failed to create day dir: %s", dir_path);
        set_sd_error("MKDIR_DAY");
        return ESP_FAIL;
    }

    // Build filenames
    const char *ext = (type == MEDIA_TYPE_IMAGE) ? "jpg" : "mp4";
    char filename[MAX_FILENAME_LEN];
    char thumb_filename[MAX_FILENAME_LEN];
    char meta_filename[MAX_FILENAME_LEN];

    snprintf(filename, sizeof(filename), "%s.%s", media_id, ext);
    snprintf(thumb_filename, sizeof(thumb_filename), "THM_%s.jpg", media_id);
    snprintf(meta_filename, sizeof(meta_filename), "META_%s.json", media_id);

    // Full paths
    char full_path[512];  // Larger buffer to avoid truncation
    char thumb_path[512];
    char meta_path[512];

    snprintf(full_path, sizeof(full_path), "%s/%s", dir_path, filename);
    snprintf(thumb_path, sizeof(thumb_path), "%s/%s", dir_path, thumb_filename);
    snprintf(meta_path, sizeof(meta_path), "%s/%s", dir_path, meta_filename);

    // Write media file
    FILE *f = fopen(full_path, "wb");
    if (!f) {
        ESP_LOGE(TAG, "Failed to open media file for writing: %s", full_path);
        snprintf(sd_last_error, sizeof(sd_last_error), "OPEN_MEDIA_%d", errno);
        return ESP_FAIL;
    }
    size_t wrote = fwrite(data, 1, data_len, f);
    fclose(f);
    if (wrote != data_len) {
        ESP_LOGE(TAG, "Failed to write media file: %s", full_path);
        set_sd_error("WRITE_MEDIA");
        return ESP_FAIL;
    }

    // Write thumbnail
    if (thumbnail && thumb_len > 0) {
        f = fopen(thumb_path, "wb");
        if (!f) {
            ESP_LOGW(TAG, "Failed to open thumbnail for writing: %s", thumb_path);
            set_sd_error("OPEN_THUMB");
        } else {
            size_t thumb_wrote = fwrite(thumbnail, 1, thumb_len, f);
            fclose(f);
            if (thumb_wrote != thumb_len) {
                ESP_LOGW(TAG, "Failed to write thumbnail: %s", thumb_path);
                set_sd_error("WRITE_THUMB");
            }
        }
    }

    // Create metadata JSON
    cJSON *meta = cJSON_CreateObject();
    cJSON_AddStringToObject(meta, "media_id", media_id);
    cJSON_AddNumberToObject(meta, "type", type);
    cJSON_AddNumberToObject(meta, "captured_at", (double)timestamp);
    cJSON_AddStringToObject(meta, "filename", filename);
    cJSON_AddStringToObject(meta, "thumb_filename", thumb_filename);
    cJSON_AddNumberToObject(meta, "size_bytes", data_len);
    cJSON_AddNumberToObject(meta, "thumb_size_bytes", thumb_len);
    cJSON_AddStringToObject(meta, "resolution", resolution);
    cJSON_AddNumberToObject(meta, "quality", quality);
    cJSON_AddNumberToObject(meta, "upload_state", UPLOAD_STATE_PENDING);

    char *meta_str = cJSON_PrintUnformatted(meta);
    f = fopen(meta_path, "w");
    if (!f) {
        ESP_LOGW(TAG, "Failed to open metadata for writing: %s", meta_path);
        set_sd_error("OPEN_META");
    } else {
        int meta_written = fprintf(f, "%s", meta_str);
        fclose(f);
        if (meta_written < 0) {
            ESP_LOGW(TAG, "Failed to write metadata: %s", meta_path);
            set_sd_error("WRITE_META");
        }
    }

    free(meta_str);
    cJSON_Delete(meta);

    // Append to index
    f = fopen(DCIM_INDEX_FILE, "a");
    if (f) {
        fprintf(f, "{\"media_id\":\"%s\",\"timestamp\":%ld,\"type\":%d}\n",
                media_id, (long)timestamp, type);
        fclose(f);
        media_count_cache++;
    } else {
        ESP_LOGW(TAG, "Failed to update index file");
        set_sd_error("INDEX_APPEND");
    }

    // Fill output metadata
    if (out_metadata) {
        strncpy(out_metadata->media_id, media_id, MAX_MEDIA_ID_LEN);
        out_metadata->type = type;
        out_metadata->captured_at = timestamp;
        strncpy(out_metadata->filename, filename, MAX_FILENAME_LEN);
        strncpy(out_metadata->thumb_filename, thumb_filename, MAX_FILENAME_LEN);
        strncpy(out_metadata->meta_filename, meta_filename, MAX_FILENAME_LEN);
        strncpy(out_metadata->full_path, full_path, MAX_PATH_LEN);
        strncpy(out_metadata->thumb_path, thumb_path, MAX_PATH_LEN);
        strncpy(out_metadata->meta_path, meta_path, MAX_PATH_LEN);
        out_metadata->size_bytes = data_len;
        out_metadata->thumb_size_bytes = thumb_len;
        out_metadata->upload_state = UPLOAD_STATE_PENDING;
        out_metadata->quality = quality;
        strncpy(out_metadata->resolution, resolution, sizeof(out_metadata->resolution));
    }

    ESP_LOGI(TAG, "Created media entry: %s (%u bytes)", media_id, data_len);
    if (sd_last_error[0] == '\0') {
        set_sd_error(NULL);
    }
    return ESP_OK;
}

/**
 * Read media file
 */
esp_err_t sd_read_media_file(const char *media_id, uint8_t **out_data, size_t *out_len) {
    if (!media_id || !out_data || !out_len) {
        return ESP_ERR_INVALID_ARG;
    }

    time_t timestamp = 0;
    media_type_t type = MEDIA_TYPE_IMAGE;
    if (!find_index_entry(media_id, &timestamp, &type)) {
        return ESP_ERR_NOT_FOUND;
    }

    media_metadata_t meta;
    load_metadata_from_path(media_id, timestamp, &meta);
    return read_file_to_buffer(meta.full_path, out_data, out_len);
}

/**
 * Read thumbnail
 */
esp_err_t sd_read_thumbnail(const char *media_id, uint8_t **out_data, size_t *out_len) {
    if (!media_id || !out_data || !out_len) {
        return ESP_ERR_INVALID_ARG;
    }

    time_t timestamp = 0;
    media_type_t type = MEDIA_TYPE_IMAGE;
    if (!find_index_entry(media_id, &timestamp, &type)) {
        return ESP_ERR_NOT_FOUND;
    }

    media_metadata_t meta;
    load_metadata_from_path(media_id, timestamp, &meta);
    return read_file_to_buffer(meta.thumb_path, out_data, out_len);
}

esp_err_t sd_read_metadata(const char *media_id, media_metadata_t *out_metadata) {
    if (!media_id || !out_metadata) {
        return ESP_ERR_INVALID_ARG;
    }

    time_t timestamp = 0;
    media_type_t type = MEDIA_TYPE_IMAGE;
    if (!find_index_entry(media_id, &timestamp, &type)) {
        return ESP_ERR_NOT_FOUND;
    }

    esp_err_t err = load_metadata_from_path(media_id, timestamp, out_metadata);
    out_metadata->type = type;
    return err;
}

/**
 * Update upload state
 */
esp_err_t sd_update_upload_state(const char *media_id, upload_state_t state) {
    // Implementation would find metadata file and update upload_state field
    ESP_LOGI(TAG, "Upload state for %s: %d", media_id, state);
    return ESP_OK;
}

typedef struct {
    const char *media_id;
} delete_by_id_ctx_t;

static bool should_delete_by_id(const char *media_id, time_t timestamp, void *ctx) {
    delete_by_id_ctx_t *state = (delete_by_id_ctx_t *)ctx;
    if (!state || !state->media_id || !media_id) {
        return false;
    }
    (void)timestamp;
    return strcmp(media_id, state->media_id) == 0;
}

typedef struct {
    time_t cutoff;
} delete_before_ctx_t;

static bool should_delete_before(const char *media_id, time_t timestamp, void *ctx) {
    delete_before_ctx_t *state = (delete_before_ctx_t *)ctx;
    if (!state || !media_id) {
        return false;
    }
    return timestamp < state->cutoff;
}

static bool should_delete_all(const char *media_id, time_t timestamp, void *ctx) {
    (void)media_id;
    (void)timestamp;
    (void)ctx;
    return true;
}

esp_err_t sd_delete_media(const char *media_id) {
    if (!media_id || media_id[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    delete_by_id_ctx_t ctx = { .media_id = media_id };
    size_t deleted = 0;
    uint64_t freed = 0;
    esp_err_t err = prune_index_entries(should_delete_by_id, &ctx, &deleted, &freed);
    if (err != ESP_OK) {
        return err;
    }
    return deleted > 0 ? ESP_OK : ESP_ERR_NOT_FOUND;
}

esp_err_t sd_clear_storage(size_t *out_deleted, uint64_t *out_freed_bytes) {
    return prune_index_entries(should_delete_all, NULL, out_deleted, out_freed_bytes);
}

esp_err_t sd_delete_media_older_than(time_t cutoff, size_t *out_deleted, uint64_t *out_freed_bytes) {
    delete_before_ctx_t ctx = { .cutoff = cutoff };
    return prune_index_entries(should_delete_before, &ctx, out_deleted, out_freed_bytes);
}

/**
 * Get storage info
 */
esp_err_t sd_get_storage_info(uint64_t *out_total, uint64_t *out_free, uint64_t *out_used) {
    if (!is_mounted) {
        return ESP_ERR_INVALID_STATE;
    }

    FATFS *fs;
    DWORD fre_clust;

    if (f_getfree("0:", &fre_clust, &fs) != FR_OK) {
        return ESP_FAIL;
    }

    uint64_t total = (uint64_t)(fs->n_fatent - 2) * fs->csize * fs->ssize;
    uint64_t free = (uint64_t)fre_clust * fs->csize * fs->ssize;

    if (out_total) *out_total = total;
    if (out_free) *out_free = free;
    if (out_used) *out_used = total - free;

    return ESP_OK;
}

/**
 * List media (simplified implementation)
 */
esp_err_t sd_list_media(
    media_metadata_t *out_list,
    size_t max_count,
    size_t offset,
    size_t *out_count,
    size_t *out_total
) {
    if (!is_mounted) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!out_list || !out_count || !out_total) {
        return ESP_ERR_INVALID_ARG;
    }

    FILE *f = fopen(DCIM_INDEX_FILE, "r");
    if (!f) {
        *out_count = 0;
        *out_total = 0;
        return ESP_OK;
    }

    size_t written = 0;
    char line[256];
    size_t line_index = 0;
    while (fgets(line, sizeof(line), f)) {
        if (line_index++ < offset) {
            continue;
        }
        if (written >= max_count) {
            break;
        }

        cJSON *entry = cJSON_Parse(line);
        if (!entry) {
            continue;
        }

        cJSON *id = cJSON_GetObjectItem(entry, "media_id");
        cJSON *ts = cJSON_GetObjectItem(entry, "timestamp");
        cJSON *type = cJSON_GetObjectItem(entry, "type");
        if (id && cJSON_IsString(id) && ts && cJSON_IsNumber(ts)) {
            time_t timestamp = (time_t)ts->valuedouble;
            media_metadata_t meta;
            load_metadata_from_path(id->valuestring, timestamp, &meta);
            meta.captured_at = timestamp;
            meta.type = (type && cJSON_IsNumber(type)) ? (media_type_t)type->valueint : MEDIA_TYPE_IMAGE;
            out_list[written++] = meta;
        }

        cJSON_Delete(entry);
    }

    fclose(f);
    *out_count = written;
    *out_total = media_count_cache;
    return ESP_OK;
}

size_t sd_get_media_count(void) {
    if (!is_mounted) {
        return 0;
    }

    return media_count_cache;
}

const char *sd_storage_last_error(void) {
    return sd_last_error;
}

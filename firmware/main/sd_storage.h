/**
 * SD Card Storage Management
 * Handles DCIM directory structure, metadata, and indexing
 */
#ifndef SD_STORAGE_H
#define SD_STORAGE_H

#include <stdint.h>
#include <stdbool.h>
#include <time.h>

// Media types
typedef enum {
    MEDIA_TYPE_IMAGE = 0,
    MEDIA_TYPE_VIDEO = 1
} media_type_t;

// Upload states
typedef enum {
    UPLOAD_STATE_PENDING = 0,
    UPLOAD_STATE_UPLOADING = 1,
    UPLOAD_STATE_COMPLETED = 2,
    UPLOAD_STATE_FAILED = 3
} upload_state_t;

// Media metadata structure
typedef struct {
    char media_id[MAX_MEDIA_ID_LEN];
    media_type_t type;
    time_t captured_at;
    char filename[MAX_FILENAME_LEN];
    char thumb_filename[MAX_FILENAME_LEN];
    char meta_filename[MAX_FILENAME_LEN];
    char full_path[MAX_PATH_LEN];
    char thumb_path[MAX_PATH_LEN];
    char meta_path[MAX_PATH_LEN];
    uint32_t size_bytes;
    uint32_t thumb_size_bytes;
    upload_state_t upload_state;
    uint8_t quality;
    char resolution[16];  // e.g., "1600x1200"
} media_metadata_t;

// SD storage functions
esp_err_t sd_storage_init(void);
esp_err_t sd_storage_deinit(void);
bool sd_storage_is_mounted(void);

// Media operations
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
);

esp_err_t sd_read_media_file(const char *media_id, uint8_t **out_data, size_t *out_len);
esp_err_t sd_read_thumbnail(const char *media_id, uint8_t **out_data, size_t *out_len);
esp_err_t sd_read_metadata(const char *media_id, media_metadata_t *out_metadata);

esp_err_t sd_update_upload_state(const char *media_id, upload_state_t state);
esp_err_t sd_delete_media(const char *media_id);
esp_err_t sd_clear_storage(size_t *out_deleted, uint64_t *out_freed_bytes);
esp_err_t sd_delete_media_older_than(time_t cutoff, size_t *out_deleted, uint64_t *out_freed_bytes);

// Listing operations
esp_err_t sd_list_media(
    media_metadata_t *out_list,
    size_t max_count,
    size_t offset,
    size_t *out_count,
    size_t *out_total
);

// Storage info
esp_err_t sd_get_storage_info(uint64_t *out_total, uint64_t *out_free, uint64_t *out_used);
size_t sd_get_media_count(void);

// Index management
esp_err_t sd_rebuild_index(void);
const char *sd_storage_last_error(void);

#endif // SD_STORAGE_H

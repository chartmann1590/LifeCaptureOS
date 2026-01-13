/**
 * Camera Capture and Thumbnail Generation
 */
#ifndef CAMERA_CAPTURE_H
#define CAMERA_CAPTURE_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_camera.h"

// Capture configuration
typedef struct {
    uint16_t width;
    uint16_t height;
    uint8_t quality;  // 10-100
    bool led_enabled;
} capture_config_t;

// Capture result
typedef struct {
    uint8_t *image_data;
    size_t image_len;
    uint8_t *thumbnail_data;
    size_t thumbnail_len;
    char resolution[16];
    bool success;
} capture_result_t;

// Camera functions
esp_err_t camera_init(void);
esp_err_t camera_deinit(void);
bool camera_is_initialized(void);

// Capture operations
esp_err_t camera_capture_image(const capture_config_t *config, capture_result_t *out_result);
void camera_free_result(capture_result_t *result);

// Thumbnail generation
esp_err_t camera_generate_thumbnail(
    const uint8_t *jpeg_data,
    size_t jpeg_len,
    uint16_t max_width,
    uint16_t max_height,
    uint8_t quality,
    uint8_t **out_thumb_data,
    size_t *out_thumb_len
);

// Resolution helpers
void camera_get_resolution_string(framesize_t size, char *out_str, size_t max_len);

#endif // CAMERA_CAPTURE_H

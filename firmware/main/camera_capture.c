/**
 * Camera Capture Implementation
 */
#include <string.h>
#include "esp_log.h"
#include "esp_camera.h"
#include "esp_psram.h"
#include "img_converters.h"

#include "lifecaptureos_config.h"
#include "camera_capture.h"

static const char *TAG = "camera";

static bool camera_initialized = false;

/**
 * Initialize ESP32-CAM
 */
esp_err_t camera_init(void) {
    if (camera_initialized) {
        ESP_LOGW(TAG, "Camera already initialized");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Initializing camera");

    bool has_psram = esp_psram_is_initialized();
    framesize_t frame_size = has_psram ? FRAMESIZE_UXGA : FRAMESIZE_VGA;
    camera_fb_location_t fb_location = has_psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    int fb_count = has_psram ? 2 : 1;

    ESP_LOGI(TAG, "PSRAM %s, frame_size=%d, fb_count=%d", has_psram ? "enabled" : "disabled", frame_size, fb_count);

    camera_config_t config = {
        .pin_pwdn = CAM_PIN_PWDN,
        .pin_reset = CAM_PIN_RESET,
        .pin_xclk = CAM_PIN_XCLK,
        .pin_sscb_sda = CAM_PIN_SIOD,
        .pin_sscb_scl = CAM_PIN_SIOC,

        .pin_d7 = CAM_PIN_D7,
        .pin_d6 = CAM_PIN_D6,
        .pin_d5 = CAM_PIN_D5,
        .pin_d4 = CAM_PIN_D4,
        .pin_d3 = CAM_PIN_D3,
        .pin_d2 = CAM_PIN_D2,
        .pin_d1 = CAM_PIN_D1,
        .pin_d0 = CAM_PIN_D0,
        .pin_vsync = CAM_PIN_VSYNC,
        .pin_href = CAM_PIN_HREF,
        .pin_pclk = CAM_PIN_PCLK,

        // Reduced XCLK to 10MHz for stability (fixes NO-SOI errors)
        .xclk_freq_hz = 10000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,

        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = frame_size,
        .jpeg_quality = DEFAULT_JPEG_QUALITY,
        .fb_count = fb_count,
        .fb_location = fb_location,
        .grab_mode = CAMERA_GRAB_LATEST
    };

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed: 0x%x", err);
        return err;
    }

    camera_initialized = true;

    // Get camera sensor
    sensor_t *s = esp_camera_sensor_get();
    if (s != NULL) {
        // Adjust settings
        s->set_brightness(s, 0);     // -2 to 2
        s->set_contrast(s, 0);       // -2 to 2
        s->set_saturation(s, 0);     // -2 to 2
        s->set_special_effect(s, 0); // 0 = no effect
        s->set_whitebal(s, 1);       // enable white balance
        s->set_awb_gain(s, 1);       // enable AWB gain
        s->set_wb_mode(s, 0);        // 0 = auto
        s->set_exposure_ctrl(s, 1);  // enable AEC
        s->set_aec2(s, 0);           // disable AEC2
        s->set_ae_level(s, 0);       // -2 to 2
        s->set_aec_value(s, 300);    // 0 to 1200
        s->set_gain_ctrl(s, 1);      // enable AGC
        s->set_agc_gain(s, 0);       // 0 to 30
        s->set_gainceiling(s, (gainceiling_t)0);  // 0 to 6
        s->set_bpc(s, 0);            // disable BPC
        s->set_wpc(s, 1);            // enable WPC
        s->set_raw_gma(s, 1);        // enable raw GMA
        s->set_lenc(s, 1);           // enable lens correction
        s->set_hmirror(s, 0);        // disable H-mirror
        s->set_vflip(s, 0);          // disable V-flip
        s->set_dcw(s, 1);            // enable downsize
        s->set_colorbar(s, 0);       // disable colorbar
    }

    ESP_LOGI(TAG, "Camera initialized successfully");
    return ESP_OK;
}

esp_err_t camera_deinit(void) {
    if (!camera_initialized) {
        return ESP_OK;
    }

    esp_err_t err = esp_camera_deinit();
    if (err == ESP_OK) {
        camera_initialized = false;
        ESP_LOGI(TAG, "Camera deinitialized");
    }

    return err;
}

bool camera_is_initialized(void) {
    return camera_initialized;
}

/**
 * Capture image and generate thumbnail
 */
esp_err_t camera_capture_image(const capture_config_t *config, capture_result_t *out_result) {
    if (!camera_initialized) {
        ESP_LOGE(TAG, "Camera not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    memset(out_result, 0, sizeof(capture_result_t));

    // Set quality
    sensor_t *s = esp_camera_sensor_get();
    if (s && config) {
        s->set_quality(s, config->quality);
    }

    // Capture frame
    ESP_LOGI(TAG, "Capturing image...");
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        ESP_LOGE(TAG, "Camera capture failed");
        out_result->success = false;
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Image captured: %u bytes, %ux%u", fb->len, fb->width, fb->height);

    // Copy image data
    out_result->image_data = (uint8_t *)malloc(fb->len);
    if (!out_result->image_data) {
        ESP_LOGE(TAG, "Failed to allocate memory for image");
        esp_camera_fb_return(fb);
        out_result->success = false;
        return ESP_ERR_NO_MEM;
    }

    memcpy(out_result->image_data, fb->buf, fb->len);
    out_result->image_len = fb->len;

    // Get resolution string
    snprintf(out_result->resolution, sizeof(out_result->resolution),
             "%ux%u", fb->width, fb->height);

    const uint8_t *thumb_source = out_result->image_data;
    size_t thumb_source_len = out_result->image_len;

    // Release the frame buffer before generating the thumbnail.
    // The thumbnail path captures another frame, which will block if fb_count=1.
    esp_camera_fb_return(fb);

    // Generate thumbnail
    esp_err_t err = camera_generate_thumbnail(
        thumb_source,
        thumb_source_len,
        THUMBNAIL_MAX_WIDTH,
        THUMBNAIL_MAX_HEIGHT,
        THUMBNAIL_QUALITY,
        &out_result->thumbnail_data,
        &out_result->thumbnail_len
    );

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Thumbnail generation failed, continuing without thumbnail");
        out_result->thumbnail_data = NULL;
        out_result->thumbnail_len = 0;
    } else {
        ESP_LOGI(TAG, "Thumbnail generated: %u bytes", out_result->thumbnail_len);
    }

    out_result->success = true;
    return ESP_OK;
}

/**
 * Free capture result
 */
void camera_free_result(capture_result_t *result) {
    if (result->image_data) {
        free(result->image_data);
        result->image_data = NULL;
    }
    if (result->thumbnail_data) {
        free(result->thumbnail_data);
        result->thumbnail_data = NULL;
    }
}

/**
 * Generate thumbnail from JPEG
 *
 * This is a simplified implementation.
 * For a production system, you'd decode JPEG, resize, and re-encode.
 * ESP32 img_converters provides jpg2rgb888 and rgb888_to_jpg functions.
 */
esp_err_t camera_generate_thumbnail(
    const uint8_t *jpeg_data,
    size_t jpeg_len,
    uint16_t max_width,
    uint16_t max_height,
    uint8_t quality,
    uint8_t **out_thumb_data,
    size_t *out_thumb_len
) {
    // Simplified thumbnail generation:
    // For MVP, we are disabling the resolution switch method as it causes instability
    // on some OV2640 modules (VGA switch crash).
    // In a future update, we should implement software resizing of the JPEG data.
    
    ESP_LOGW(TAG, "Thumbnail generation disabled for stability");
    *out_thumb_data = NULL;
    *out_thumb_len = 0;
    return ESP_OK;
}

void camera_get_resolution_string(framesize_t size, char *out_str, size_t max_len) {
    switch (size) {
        case FRAMESIZE_UXGA:  snprintf(out_str, max_len, "1600x1200"); break;
        case FRAMESIZE_SXGA:  snprintf(out_str, max_len, "1280x1024"); break;
        case FRAMESIZE_XGA:   snprintf(out_str, max_len, "1024x768"); break;
        case FRAMESIZE_SVGA:  snprintf(out_str, max_len, "800x600"); break;
        case FRAMESIZE_VGA:   snprintf(out_str, max_len, "640x480"); break;
        default:              snprintf(out_str, max_len, "unknown"); break;
    }
}

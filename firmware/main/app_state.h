/**
 * Runtime app state helpers
 */
#ifndef APP_STATE_H
#define APP_STATE_H

#include <time.h>
#include "config_manager.h"

bool app_is_capture_active(void);
void app_apply_config(const device_config_t *new_config);
void start_capture(void);
void stop_capture(void);
time_t app_get_last_capture_timestamp(void);
uint32_t app_get_capture_attempts(void);
uint32_t app_get_capture_successes(void);
uint32_t app_get_capture_failures(void);
const char *app_get_last_capture_error(void);
uint32_t app_get_capture_timer_ticks(void);

#endif // APP_STATE_H

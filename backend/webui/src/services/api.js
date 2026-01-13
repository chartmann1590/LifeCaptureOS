/**
 * API client for communicating with FastAPI backend
 */

const API_BASE = '';

/**
 * Fetch wrapper with error handling
 */
async function fetchJSON(url, options = {}) {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorData;
    try {
      errorData = await response.json();
    } catch {
      errorData = { detail: `HTTP ${response.status}: ${response.statusText}` };
    }
    const errorMessage = errorData.detail || errorData.message || `HTTP ${response.status}`;
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Get list of all devices
 */
export async function getDevices() {
  const data = await fetchJSON('/media/devices/list');
  return data.devices || [];
}

/**
 * Get detailed device information
 */
export async function getDeviceDetails(deviceId) {
  const data = await fetchJSON(`/media/devices/${deviceId}`);
  return data.device;
}

/**
 * Get list of media items
 * @param {Object} params - Query parameters
 * @param {string} params.device_id - Filter by device ID
 * @param {string} params.type - Filter by type (image/video)
 * @param {number} params.limit - Max items to return
 * @param {number} params.offset - Pagination offset
 * @param {string} params.start_date - ISO 8601 datetime string (filter media captured after this date)
 * @param {string} params.end_date - ISO 8601 datetime string (filter media captured before this date)
 * @param {string} params.search - String to search in ai_caption and ai_tags fields
 */
export async function getMedia({ device_id, type, limit = 50, offset = 0, start_date, end_date, search } = {}) {
  const params = new URLSearchParams();
  if (device_id) params.append('device_id', device_id);
  if (type) params.append('type', type);
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  if (search) params.append('search', search);
  params.append('limit', limit.toString());
  params.append('offset', offset.toString());

  const data = await fetchJSON(`/media/?${params.toString()}`);
  return data;
}

/**
 * Get media item by ID
 */
export async function getMediaItem(mediaId) {
  return fetchJSON(`/media/${mediaId}`);
}

/**
 * Get thumbnail URL for a media item
 */
export function getMediaThumbnailUrl(mediaId) {
  return `${API_BASE}/media/${mediaId}/thumb`;
}

/**
 * Get full image/file URL for a media item
 */
export function getMediaFileUrl(mediaId) {
  return `${API_BASE}/media/${mediaId}/file`;
}

/**
 * Re-analyze media with AI
 */
export async function reanalyzeMedia(mediaId) {
  return fetchJSON(`/media/${mediaId}/reanalyze`, {
    method: 'POST',
  });
}

/**
 * Get timezone setting
 */
export async function getTimezone() {
  return fetchJSON('/api/settings/timezone');
}

/**
 * Update timezone setting
 */
export async function updateTimezone(timezone) {
  return fetchJSON('/api/settings/timezone', {
    method: 'PUT',
    body: JSON.stringify({ timezone }),
  });
}

/**
 * Get daily summaries enabled setting
 */
export async function getDailySummariesEnabled() {
  return fetchJSON('/api/settings/daily-summaries-enabled');
}

/**
 * Update daily summaries enabled setting
 */
export async function updateDailySummariesEnabled(enabled) {
  return fetchJSON('/api/settings/daily-summaries-enabled', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });
}

/**
 * Get list of daily summaries
 */
export async function getDailySummaries(limit = 50, offset = 0) {
  const params = new URLSearchParams();
  params.append('limit', limit.toString());
  params.append('offset', offset.toString());
  return fetchJSON(`/ai/daily-summaries?${params.toString()}`);
}

/**
 * Get daily summary by date (YYYY-MM-DD)
 */
export async function getDailySummary(date) {
  return fetchJSON(`/ai/daily-summaries/${date}`);
}

/**
 * Generate daily summary
 */
export async function generateDailySummary(date, endTime, allowDuplicate = false) {
  return fetchJSON('/ai/daily-summaries/generate', {
    method: 'POST',
    body: JSON.stringify({ date, end_time: endTime, allow_duplicate: allowDuplicate }),
  });
}

/**
 * Get daily summary video URL
 */
export function getDailySummaryVideoUrl(date) {
  return `${API_BASE}/ai/daily-summaries/${date}/video`;
}

/**
 * Check if daily summary exists for a date
 */
export async function checkDailySummaryStatus(date) {
  return fetchJSON(`/ai/daily-summaries/${date}/status`);
}

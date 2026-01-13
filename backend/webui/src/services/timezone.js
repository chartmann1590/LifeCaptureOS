/**
 * Timezone service for fetching and managing timezone settings
 */

const TIMEZONE_CACHE_KEY = 'lifeCaptureOS_timezone';

/**
 * Get timezone from API or cache
 */
export async function getTimezone() {
  // Check cache first
  const cached = localStorage.getItem(TIMEZONE_CACHE_KEY);
  if (cached) {
    return cached;
  }

  try {
    const response = await fetch('/api/settings/timezone');
    if (response.ok) {
      const data = await response.json();
      const timezone = data.timezone || 'UTC';
      localStorage.setItem(TIMEZONE_CACHE_KEY, timezone);
      return timezone;
    }
  } catch (error) {
    console.warn('Failed to fetch timezone from API:', error);
  }

  // Fallback to browser timezone
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

/**
 * Update timezone setting
 */
export async function updateTimezone(timezone) {
  try {
    const response = await fetch('/api/settings/timezone', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ timezone }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    localStorage.setItem(TIMEZONE_CACHE_KEY, data.timezone);
    return data.timezone;
  } catch (error) {
    console.error('Failed to update timezone:', error);
    throw error;
  }
}

/**
 * Format a date string using the configured timezone
 */
export async function formatDate(dateString, options = {}) {
  if (!dateString) return 'Never';

  const timezone = await getTimezone();
  const date = new Date(dateString);

  const defaultOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: timezone,
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(date);
}

/**
 * Format a date string for display (short format)
 */
export async function formatDateShort(dateString) {
  return formatDate(dateString, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Format a date string with time
 */
export async function formatDateTime(dateString) {
  return formatDate(dateString, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a date string for gallery (date + time on separate lines)
 */
export async function formatDateForGallery(dateString) {
  if (!dateString) return '';

  const timezone = await getTimezone();
  const date = new Date(dateString);

  const dateFormatter = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: timezone,
  });

  const timeFormatter = new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: timezone,
  });

  return dateFormatter.format(date) + ' ' + timeFormatter.format(date);
}

/**
 * Clear timezone cache (useful when timezone is updated)
 */
export function clearTimezoneCache() {
  localStorage.removeItem(TIMEZONE_CACHE_KEY);
}

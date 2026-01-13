"""Timezone utility functions for converting UTC datetimes to configured timezone."""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    try:
        import pytz
        ZoneInfo = None
    except ImportError:
        pytz = None
        ZoneInfo = None

from app.models import SystemSettings
from app.config import settings

logger = logging.getLogger(__name__)


def get_timezone(db: Optional[Session] = None) -> str:
    """
    Get the configured timezone.
    
    Checks database first, then falls back to config/env var.
    
    Args:
        db: Optional database session. If provided, checks database for timezone setting.
        
    Returns:
        IANA timezone string (e.g., "America/New_York", "UTC")
    """
    if db:
        try:
            timezone_setting = db.query(SystemSettings).filter(
                SystemSettings.key == "timezone"
            ).first()
            
            if timezone_setting:
                return timezone_setting.value
        except Exception as e:
            logger.warning(f"Failed to get timezone from database: {e}")
    
    # Fallback to config/env var
    return settings.timezone


def get_timezone_obj(timezone_str: Optional[str] = None, db: Optional[Session] = None):
    """
    Get timezone object for the configured timezone.
    
    Args:
        timezone_str: Optional timezone string. If None, fetches from database/config.
        db: Optional database session for fetching timezone setting.
        
    Returns:
        timezone object (ZoneInfo or pytz timezone)
    """
    if timezone_str is None:
        timezone_str = get_timezone(db)
    
    # Validate timezone string
    if not timezone_str:
        timezone_str = "UTC"
    
    try:
        if ZoneInfo:
            # Python 3.9+
            return ZoneInfo(timezone_str)
        elif pytz:
            # Fallback for Python < 3.9
            return pytz.timezone(timezone_str)
        else:
            logger.warning("No timezone library available. Using UTC.")
            return timezone.utc
    except Exception as e:
        logger.warning(f"Invalid timezone '{timezone_str}': {e}. Falling back to UTC.")
        if ZoneInfo:
            return ZoneInfo("UTC")
        elif pytz:
            return pytz.UTC
        else:
            return timezone.utc


def to_timezone(dt: datetime, timezone_str: Optional[str] = None, db: Optional[Session] = None) -> datetime:
    """
    Convert a datetime to the configured timezone.
    
    Args:
        dt: Datetime to convert (assumed to be UTC if timezone-naive)
        timezone_str: Optional timezone string. If None, uses configured timezone.
        db: Optional database session for fetching timezone setting.
        
    Returns:
        Datetime in the configured timezone
    """
    # Ensure datetime is timezone-aware (assume UTC if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Get target timezone
    tz = get_timezone_obj(timezone_str, db)
    
    # Convert to target timezone
    if ZoneInfo:
        # Python 3.9+ with zoneinfo
        return dt.astimezone(tz)
    elif pytz:
        # Python < 3.9 with pytz
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(tz)
    else:
        # Fallback: return as-is (shouldn't happen if dependencies are installed)
        return dt


def format_datetime_iso(dt: datetime, timezone_str: Optional[str] = None, db: Optional[Session] = None) -> Optional[str]:
    """
    Format a datetime as ISO 8601 string in the configured timezone.
    
    Args:
        dt: Datetime to format (assumed to be UTC if timezone-naive)
        timezone_str: Optional timezone string. If None, uses configured timezone.
        db: Optional database session for fetching timezone setting.
        
    Returns:
        ISO 8601 formatted datetime string, or None if dt is None
    """
    if dt is None:
        return None
    
    try:
        dt_tz = to_timezone(dt, timezone_str, db)
        return dt_tz.isoformat()
    except Exception as e:
        logger.warning(f"Error formatting datetime: {e}. Returning UTC ISO format.")
        # Fallback to UTC if timezone conversion fails
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception as e2:
            logger.error(f"Critical error formatting datetime: {e2}")
            # Last resort: return as string representation
            return str(dt)


def validate_timezone(timezone_str: str) -> bool:
    """
    Validate that a timezone string is valid.
    
    Args:
        timezone_str: IANA timezone string to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not timezone_str:
        return False
    
    # Try ZoneInfo first (Python 3.9+)
    if ZoneInfo:
        try:
            ZoneInfo(timezone_str)
            return True
        except Exception as e:
            # ZoneInfo failed - might be missing tzdata on Windows
            logger.debug(f"ZoneInfo validation failed for '{timezone_str}': {e}. Trying pytz fallback.")
            # Fall through to try pytz
    
    # Try pytz as fallback
    if pytz:
        try:
            pytz.timezone(timezone_str)
            return True
        except Exception as e:
            logger.debug(f"pytz validation failed for '{timezone_str}': {e}")
            return False
    
    # No timezone library available - only accept UTC
    logger.warning("No timezone library available. Only UTC is supported.")
    return timezone_str == "UTC"

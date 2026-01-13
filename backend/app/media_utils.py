"""Helpers for parsing media timestamps."""

import re
from datetime import datetime, timezone
from typing import Optional

_MEDIA_ID_TIMESTAMP_RE = re.compile(r"^[A-Z]+_(\d{9,})_")


def parse_epoch_timestamp(value: Optional[object]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if timestamp > 1_000_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def parse_media_id_timestamp(media_id: Optional[str]) -> Optional[datetime]:
    if not media_id:
        return None
    match = _MEDIA_ID_TIMESTAMP_RE.match(media_id)
    if not match:
        return None
    return parse_epoch_timestamp(match.group(1))


def resolve_captured_at(
    epoch_value: Optional[object],
    media_id: Optional[str],
    fallback: Optional[datetime] = None
) -> datetime:
    captured_at = parse_epoch_timestamp(epoch_value) or parse_media_id_timestamp(media_id)
    if captured_at is None:
        captured_at = fallback or datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return captured_at

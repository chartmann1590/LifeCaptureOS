"""Chat service for querying media with AI assistance."""
import logging
import json
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models import Media, UploadState
from app.timezone_utils import get_timezone_obj, to_timezone

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling chat queries about media."""

    def __init__(self, db: Session):
        self.db = db

    def extract_time_filters(self, query: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Extract time range filters from natural language query.
        
        Returns:
            Tuple of (start_time, end_time) in UTC. Both can be None.
        """
        query_lower = query.lower()
        now_utc = datetime.now(timezone.utc)
        
        # Get configured timezone for local time calculations
        try:
            tz = get_timezone_obj(db=self.db)
            now_local = to_timezone(now_utc, db=self.db)
        except Exception:
            tz = timezone.utc
            now_local = now_utc

        # "this morning" - today before noon
        if "this morning" in query_lower:
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            noon = today_start.replace(hour=12)
            # Convert to UTC
            if tz != timezone.utc:
                today_start_utc = today_start.astimezone(timezone.utc)
                noon_utc = noon.astimezone(timezone.utc)
            else:
                today_start_utc = today_start
                noon_utc = noon
            return (today_start_utc, noon_utc)

        # "today" - from start of today to now
        if "today" in query_lower:
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            if tz != timezone.utc:
                today_start_utc = today_start.astimezone(timezone.utc)
            else:
                today_start_utc = today_start
            return (today_start_utc, now_utc)

        # "yesterday" - entire yesterday
        if "yesterday" in query_lower:
            yesterday_start = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59)
            if tz != timezone.utc:
                yesterday_start_utc = yesterday_start.astimezone(timezone.utc)
                yesterday_end_utc = yesterday_end.astimezone(timezone.utc)
            else:
                yesterday_start_utc = yesterday_start
                yesterday_end_utc = yesterday_end
            return (yesterday_start_utc, yesterday_end_utc)

        # "last week" - 7 days ago to now
        if "last week" in query_lower or "past week" in query_lower:
            week_ago = now_utc - timedelta(days=7)
            return (week_ago, now_utc)

        # "this week" - start of current week (Monday) to now
        if "this week" in query_lower:
            days_since_monday = now_local.weekday()
            week_start = (now_local - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            if tz != timezone.utc:
                week_start_utc = week_start.astimezone(timezone.utc)
            else:
                week_start_utc = week_start
            return (week_start_utc, now_utc)

        # "this month" - start of current month to now
        if "this month" in query_lower:
            month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if tz != timezone.utc:
                month_start_utc = month_start.astimezone(timezone.utc)
            else:
                month_start_utc = month_start
            return (month_start_utc, now_utc)

        # "last month" - entire previous month
        if "last month" in query_lower:
            if now_local.month == 1:
                last_month_start = now_local.replace(year=now_local.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                last_month_start = now_local.replace(month=now_local.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Get last day of previous month
            if last_month_start.month == 12:
                next_month = last_month_start.replace(year=last_month_start.year + 1, month=1)
            else:
                next_month = last_month_start.replace(month=last_month_start.month + 1)
            last_month_end = next_month - timedelta(seconds=1)
            
            if tz != timezone.utc:
                last_month_start_utc = last_month_start.astimezone(timezone.utc)
                last_month_end_utc = last_month_end.astimezone(timezone.utc)
            else:
                last_month_start_utc = last_month_start
                last_month_end_utc = last_month_end
            return (last_month_start_utc, last_month_end_utc)

        # No time filter found
        return (None, None)

    def query_media(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Media]:
        """
        Query media items with optional time filters.
        
        Args:
            start_time: Optional start time (UTC)
            end_time: Optional end time (UTC)
            limit: Maximum number of items to return
        
        Returns:
            List of Media items, ordered by captured_at descending
        """
        query = self.db.query(Media).filter(
            Media.upload_state == UploadState.COMPLETED,
            Media.ai_caption.isnot(None),  # Only include analyzed media
            Media.ai_caption != ""  # Exclude empty captions
        )

        if start_time:
            query = query.filter(Media.captured_at >= start_time)
        if end_time:
            query = query.filter(Media.captured_at <= end_time)

        items = query.order_by(desc(Media.captured_at)).limit(limit).all()
        return items

    def format_media_context(self, media_items: List[Media]) -> str:
        """
        Format media items into context string for AI prompt.
        
        Args:
            media_items: List of Media items
        
        Returns:
            Formatted context string
        """
        if not media_items:
            return "No photos found in the specified time range."

        context_parts = []
        for item in media_items:
            # Parse tags
            tags = []
            if item.ai_tags_json:
                try:
                    tags = json.loads(item.ai_tags_json)
                except:
                    pass

            # Format timestamp
            try:
                tz = get_timezone_obj(db=self.db)
                dt_local = to_timezone(item.captured_at, db=self.db)
                time_str = dt_local.strftime("%Y-%m-%d %H:%M")
            except:
                time_str = item.captured_at.isoformat()

            # Build description
            desc_parts = [f"Photo captured at {time_str}: {item.ai_caption}"]
            if tags:
                desc_parts.append(f"Tags: {', '.join(tags)}")
            
            context_parts.append(" - ".join(desc_parts))

        return "\n".join(context_parts)

    def build_media_context(self, query: str, limit: int = 50) -> Tuple[str, List[int]]:
        """
        Build media context from query by extracting time filters and querying media.
        
        Args:
            query: User query string
            limit: Maximum number of media items to include
        
        Returns:
            Tuple of (context_string, media_ids_list)
        """
        # Extract time filters
        start_time, end_time = self.extract_time_filters(query)

        # Query media
        media_items = self.query_media(start_time=start_time, end_time=end_time, limit=limit)

        # Format context
        context = self.format_media_context(media_items)

        # Extract media IDs
        media_ids = [item.id for item in media_items]

        return (context, media_ids)

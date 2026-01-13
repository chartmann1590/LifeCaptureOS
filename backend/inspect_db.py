import asyncio
import logging
import sys
import os
from sqlalchemy import func

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models import Media

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect():
    db = SessionLocal()
    try:
        count = db.query(Media).count()
        logger.info(f"Total Media items in DB: {count}")
        
        if count > 0:
            first = db.query(Media).first()
            logger.info(f"First item: ID={first.id}, Date={first.captured_at}, Path={first.media_path}, Caption={first.ai_caption}")
            
            # Check for 2026-01-11 specifically
            from datetime import datetime
            start = datetime(2026, 1, 11, 0, 0, 0)
            end = datetime(2026, 1, 11, 23, 59, 59)
            
            day_count = db.query(Media).filter(Media.captured_at >= start, Media.captured_at <= end).count()
            logger.info(f"Count for 2026-01-11: {day_count}")

            # Check for ANY captions
            caption_count = db.query(Media).filter(Media.ai_caption.isnot(None)).count()
            logger.info(f"Total items with captions: {caption_count}")
            
            # Check for 2026-01-12
            start_12 = datetime(2026, 1, 12, 0, 0, 0)
            end_12 = datetime(2026, 1, 12, 23, 59, 59)
            day_count_12 = db.query(Media).filter(Media.captured_at >= start_12, Media.captured_at <= end_12).count()
            logger.info(f"Count for 2026-01-12: {day_count_12}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inspect()

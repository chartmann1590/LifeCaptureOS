import asyncio
import logging
import sys
import os
from datetime import date, timedelta

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.video_service import VideoGenerationService
from app.models import DailySummaryJob, DailySummaryJobStatus

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_debug():
    logger.info("Starting debug video generation...")
    
    db = SessionLocal()
    service = VideoGenerationService()
    
    # Try to generate for 2026-01-11 (which failed before)
    target_date = date(2026, 1, 11)
    logger.info(f"Target date: {target_date}")
    
    # Create a dummy job
    job = DailySummaryJob(
        date=target_date.strftime("%Y-%m-%d"),
        status=DailySummaryJobStatus.QUEUED,
        allow_duplicate=True
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    try:
        logger.info("Calling generate_daily_summary...")
        await service.generate_daily_summary(
            target_date=target_date,
            job=job,
            db=db
        )
        logger.info("Generation completed successfully!")
        
    except Exception as e:
        logger.error(f"Generation FAILED with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_debug())

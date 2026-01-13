import asyncio
import logging
import sys
import os
from datetime import date

# Add current directory to path
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.video_service import VideoGenerationService
from app.models import DailySummaryJob, DailySummaryJobStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_debug():
    logger.info("Starting debug regeneration...")
    
    db = SessionLocal()
    service = VideoGenerationService()
    
    # Target date that already has a summary (Jan 11)
    target_date = date(2026, 1, 11)
    logger.info(f"Target date: {target_date}")
    
    # Create a job with allow_duplicate=True
    job = DailySummaryJob(
        date=target_date.strftime("%Y-%m-%d"),
        status=DailySummaryJobStatus.QUEUED,
        allow_duplicate=True # FORCE REGENERATION
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    try:
        logger.info(f"Calling generate_daily_summary with Job ID {job.id} and allow_duplicate={job.allow_duplicate}...")
        await service.generate_daily_summary(
            target_date=target_date,
            job=job,
            db=db
        )
        logger.info("Regeneration completed successfully!")
        
    except Exception as e:
        logger.error(f"Regeneration FAILED with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_debug())

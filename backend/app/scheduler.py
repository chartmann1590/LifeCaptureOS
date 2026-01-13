"""Scheduled task system for daily summary generation."""
import logging
from datetime import datetime, date, timedelta, time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SystemSettings, DailySummaryJob, DailySummaryJobStatus
from app.video_service import VideoGenerationService

logger = logging.getLogger(__name__)


class DailySummaryScheduler:
    """Scheduler for daily summary video generation."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.video_service = VideoGenerationService()
        self._is_running = False
    
    def start(self, generation_time: str = "05:00"):
        """Start the scheduler."""
        if self._is_running:
            logger.warning("Scheduler is already running")
            return
        
        # Parse generation time (HH:MM format)
        try:
            hour, minute = map(int, generation_time.split(':'))
        except ValueError:
            logger.error(f"Invalid generation time format: {generation_time}. Using default 05:00")
            hour, minute = 5, 0
        
        # Schedule daily task
        self.scheduler.add_job(
            self._generate_daily_summary_task,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_summary_generation',
            name='Generate Daily Summary',
            replace_existing=True
        )
        
        self.scheduler.start()
        self._is_running = True
        logger.info(f"Scheduler started. Daily summaries will be generated at {generation_time}")
    
    def stop(self):
        """Stop the scheduler."""
        if not self._is_running:
            return
        
        self.scheduler.shutdown()
        self._is_running = False
        logger.info("Scheduler stopped")
    
    async def _generate_daily_summary_task(self):
        """Task to generate daily summary for previous day."""
        db = SessionLocal()
        job = None  # Initialize job outside try block

        try:
            # Check if daily summaries are enabled
            setting = db.query(SystemSettings).filter(
                SystemSettings.key == "daily_summaries_enabled"
            ).first()
            
            enabled = True  # Default to enabled
            if setting:
                enabled = setting.value.lower() == "true"
            
            if not enabled:
                logger.info("Daily summaries are disabled. Skipping generation.")
                return
            
            # Generate summary for previous day
            yesterday = date.today() - timedelta(days=1)
            logger.info(f"Starting scheduled daily summary generation for {yesterday}")

            # Create DailySummaryJob
            job = DailySummaryJob(
                date=yesterday.strftime("%Y-%m-%d"),
                status=DailySummaryJobStatus.QUEUED,
                allow_duplicate=False # Scheduled tasks don't allow duplicates
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            await self.video_service.generate_daily_summary(
                target_date=yesterday,
                job=job,
                end_time=None,
                db=db
            )
            # The video_service updates the job status, so no need to do it here for success
                
        except Exception as e:
            logger.error(f"Error in daily summary generation task for {yesterday}: {e}", exc_info=True)
            if job and job.status != DailySummaryJobStatus.COMPLETED: # Only update if not already completed by video service
                job.status = DailySummaryJobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now()
                db.add(job)
                db.commit()
        finally:
            db.close()
    
    def trigger_manual_generation(self, target_date: Optional[date] = None, allow_duplicate: bool = True) -> bool:
        """
        Manually trigger generation (for testing or API calls).
        This runs asynchronously and doesn't wait for completion.
        
        Args:
            target_date: Date to generate for (defaults to yesterday)
            allow_duplicate: Whether to generate a new summary even if one exists.
            
        Returns:
            True if task was scheduled successfully
        """
        if not self._is_running:
            logger.warning("Scheduler is not running. Cannot trigger manual generation.")
            return False
        
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        db = SessionLocal()
        try:
            # Create DailySummaryJob
            job = DailySummaryJob(
                date=target_date.strftime("%Y-%m-%d"),
                status=DailySummaryJobStatus.QUEUED,
                allow_duplicate=allow_duplicate
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            # Schedule immediate job to call the internal task
            self.scheduler.add_job(
                self._manual_generate_task,
                trigger='date',
                run_date=datetime.now(),
                id=f'manual_summary_{target_date}_{job.id}',
                name=f'Manual Daily Summary for {target_date} (Job ID: {job.id})',
                args=[target_date, job.id], # Pass job ID to retrieve it in the task
                replace_existing=False # Don't replace existing manual jobs
            )
            
            logger.info(f"Manually triggered daily summary generation for {target_date} (Job ID: {job.id})")
            return True
        except Exception as e:
            logger.error(f"Error triggering manual generation: {e}", exc_info=True)
            db.rollback()
            return False
        finally:
            db.close()

    async def _manual_generate_task(self, target_date: date, job_id: int):
        """Internal task to execute manual generation."""
        db = SessionLocal()
        job = None
        try:
            job = db.query(DailySummaryJob).filter(DailySummaryJob.id == job_id).first()
            if not job:
                logger.error(f"Manual generation task: Job {job_id} not found.")
                return

            logger.info(f"Executing manual daily summary generation for {target_date} (Job ID: {job_id})")
            await self.video_service.generate_daily_summary(
                target_date=target_date,
                job=job,
                end_time=None,
                db=db
            )
        except Exception as e:
            logger.error(f"Error in manual daily summary generation task for {target_date} (Job ID: {job_id}): {e}", exc_info=True)
            if job and job.status != DailySummaryJobStatus.COMPLETED:
                job.status = DailySummaryJobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now()
                db.add(job)
                db.commit()
        finally:
            db.close()



# Global scheduler instance
_scheduler_instance: Optional[DailySummaryScheduler] = None


def get_scheduler() -> DailySummaryScheduler:
    """Get the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = DailySummaryScheduler()
    return _scheduler_instance

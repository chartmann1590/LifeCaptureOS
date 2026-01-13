"""Daily summaries API endpoints."""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.database import get_db
from app.models import DailySummary, Media, MediaType, DailySummaryJob, DailySummaryJobStatus
from app.config import settings
from sqlalchemy import and_
from app.video_service import VideoGenerationService
from app.scheduler import get_scheduler
from app.timezone_utils import format_datetime_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/daily-summaries", tags=["daily-summaries"])


class DailySummaryItem(BaseModel):
    """Daily summary response model."""
    id: int
    date: str
    video_path: str
    memory_ids: List[int]
    music_track_id: Optional[str]
    music_track_title: Optional[str]
    day_summary: Optional[str]
    generated_at: str
    expires_at: Optional[str]
    duration_seconds: Optional[int]
    file_size_bytes: Optional[int]

    class Config:
        from_attributes = True


class DailySummaryListResponse(BaseModel):
    """Daily summary list response."""
    ok: bool = True
    total: int
    limit: int
    offset: int
    items: List[DailySummaryItem]


class GenerateSummaryRequest(BaseModel):
    """Request to generate a daily summary."""
    date: Optional[str] = None  # YYYY-MM-DD format
    end_time: Optional[str] = None  # ISO 8601 datetime
    allow_duplicate: bool = False


class DailySummaryJobStatusResponse(BaseModel):
    ok: bool = True
    exists: bool
    status: Optional[DailySummaryJobStatus] = None
    job_id: Optional[int] = None
    summary_id: Optional[int] = None
    error_message: Optional[str] = None
    requested_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # If a DailySummary exists, provide its info
    generated_at: Optional[str] = None
    duration_seconds: Optional[int] = None

class GenerateSummaryResponse(BaseModel):
    """Response for summary generation request."""
    ok: bool
    message: str
    date: str


async def _list_daily_summaries_impl(
    limit: int,
    offset: int,
    db: Session
) -> DailySummaryListResponse:
    """Implementation for listing daily summaries."""
    # Get total count
    total = db.query(DailySummary).count()
    
    # Get items (newest first)
    items = db.query(DailySummary).order_by(
        desc(DailySummary.date),
        desc(DailySummary.generated_at)
    ).limit(limit).offset(offset).all()
    
    # Convert to response models
    response_items = []
    for item in items:
        import json
        memory_ids = json.loads(item.memory_ids) if item.memory_ids else []
        
        response_items.append(DailySummaryItem(
            id=item.id,
            date=item.date,
            video_path=item.video_path,
            memory_ids=memory_ids,
            music_track_id=item.music_track_id,
            music_track_title=item.music_track_title,
            day_summary=item.day_summary,
            generated_at=format_datetime_iso(item.generated_at, db=db),
            expires_at=format_datetime_iso(item.expires_at, db=db) if item.expires_at else None,
            duration_seconds=item.duration_seconds,
            file_size_bytes=item.file_size_bytes
        ))
    
    return DailySummaryListResponse(
        ok=True,
        total=total,
        limit=limit,
        offset=offset,
        items=response_items
    )


@router.get("", response_model=DailySummaryListResponse)
@router.get("/", response_model=DailySummaryListResponse)
async def list_daily_summaries(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List all daily summaries (paginated)."""
    return await _list_daily_summaries_impl(limit, offset, db)


@router.get("/{summary_date}", response_model=DailySummaryItem)
async def get_daily_summary(
    summary_date: str,  # YYYY-MM-DD format
    db: Session = Depends(get_db)
):
    """Get specific daily summary by date."""
    summary = db.query(DailySummary).filter(
        DailySummary.date == summary_date
    ).order_by(desc(DailySummary.generated_at)).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Daily summary not found for date: {summary_date}"
        )
    
    import json
    memory_ids = json.loads(summary.memory_ids) if summary.memory_ids else []
    
    return DailySummaryItem(
        id=summary.id,
        date=summary.date,
        video_path=summary.video_path,
        memory_ids=memory_ids,
        music_track_id=summary.music_track_id,
        music_track_title=summary.music_track_title,
        day_summary=summary.day_summary,
        generated_at=format_datetime_iso(summary.generated_at, db=db),
        expires_at=format_datetime_iso(summary.expires_at, db=db) if summary.expires_at else None,
        duration_seconds=summary.duration_seconds,
        file_size_bytes=summary.file_size_bytes
    )


@router.post("/generate", response_model=GenerateSummaryResponse)
async def generate_daily_summary(
    request: GenerateSummaryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Manually trigger daily summary generation."""
    try:
        # Parse date
        if request.date:
            try:
                target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid date format: {request.date}. Use YYYY-MM-DD format."
                )
        else:
            # Default to yesterday
            target_date = date.today() - timedelta(days=1)
        
        # Parse end_time if provided
        end_time = None
        if request.end_time:
            try:
                end_time = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid end_time format: {request.end_time}. Use ISO 8601 format."
                )
        
        # Trigger generation via scheduler (which creates and manages DailySummaryJob)
        scheduler = get_scheduler()
        
        # We don't pass end_time to trigger_manual_generation currently, it defaults to end of day.
        # If specific end_time handling is needed for manual triggers, scheduler.trigger_manual_generation
        # would need to be updated. For now, we'll proceed assuming it's not critical for manual.
        
        if not scheduler.trigger_manual_generation(
            target_date=target_date,
            allow_duplicate=request.allow_duplicate
        ):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to trigger daily summary generation via scheduler."
            )
        
        return GenerateSummaryResponse(
            ok=True,
            message=f"Daily summary generation for {target_date} has been triggered and is processing in the background.",
            date=target_date.strftime("%Y-%m-%d")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering summary generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error triggering generation: {str(e)}"
        )


@router.get("/{summary_date}/video")
async def get_daily_summary_video(
    summary_date: str,
    db: Session = Depends(get_db)
):
    """Stream daily summary video file."""
    summary = db.query(DailySummary).filter(
        DailySummary.date == summary_date
    ).order_by(desc(DailySummary.generated_at)).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Daily summary not found for date: {summary_date}"
        )
    
    video_path = settings.storage_path / summary.video_path
    
    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found"
        )
    
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"daily_summary_{summary_date}.mp4"
    )


@router.get("/{summary_date}/status", response_model=DailySummaryJobStatusResponse)
async def get_generation_status(
    summary_date: str,
    db: Session = Depends(get_db)
):
    """Get the generation status for a daily summary video by date."""
    
    # Try to find a DailySummaryJob first
    job = db.query(DailySummaryJob).filter(
        DailySummaryJob.date == summary_date
    ).order_by(desc(DailySummaryJob.requested_at)).first() # Get the latest job for this date
    
    if job:
        response_data = {
            "ok": True,
            "exists": True,
            "job_id": job.id,
            "status": job.status,
            "summary_id": job.summary_id,
            "error_message": job.error_message,
            "requested_at": format_datetime_iso(job.requested_at, db=db),
            "started_at": format_datetime_iso(job.started_at, db=db) if job.started_at else None,
            "completed_at": format_datetime_iso(job.completed_at, db=db) if job.completed_at else None,
        }
        
        # If the job is completed and linked to a summary, also return summary details
        if job.summary_id:
            summary = db.query(DailySummary).filter(DailySummary.id == job.summary_id).first()
            if summary:
                response_data["generated_at"] = format_datetime_iso(summary.generated_at, db=db)
                response_data["duration_seconds"] = summary.duration_seconds
        
        return DailySummaryJobStatusResponse(**response_data)
    else:
        # If no job is found, check if a DailySummary (e.g., legacy or very old completed) exists
        summary = db.query(DailySummary).filter(
            DailySummary.date == summary_date
        ).order_by(desc(DailySummary.generated_at)).first()
        
        if summary:
            return DailySummaryJobStatusResponse(
                ok=True,
                exists=True,
                status=DailySummaryJobStatus.COMPLETED, # Assume completed if only summary exists
                summary_id=summary.id,
                generated_at=format_datetime_iso(summary.generated_at, db=db),
                duration_seconds=summary.duration_seconds,
                message=f"No job record found, but summary exists for {summary_date}."
            )
        else:
            return DailySummaryJobStatusResponse(
                ok=True,
                exists=False,
                status=None,
                message=f"No summary or job found for {summary_date}"
            )

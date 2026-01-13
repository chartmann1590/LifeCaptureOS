"""Media browsing and management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import json

from app.database import get_db
from app.models import Device, Media, MediaType, UploadState
from app.config import settings
from app.ollama_service import OllamaService
from app.timezone_utils import format_datetime_iso

router = APIRouter(prefix="/media", tags=["media"])


class MediaItem(BaseModel):
    """Media item response model."""
    id: int
    device_id: str
    media_id: str
    type: str
    captured_at: str
    uploaded_at: str
    filename: str
    thumb_filename: Optional[str]
    size_bytes: Optional[int]
    thumb_size_bytes: Optional[int]
    resolution: Optional[str]
    upload_state: str
    upload_progress: float
    ai_caption: Optional[str]
    ai_tags: Optional[List[str]]
    ai_confidence: Optional[float]
    ai_analyzed_at: Optional[str]

    class Config:
        from_attributes = True


class MediaListResponse(BaseModel):
    """Media list response."""
    ok: bool = True
    total: int
    limit: int
    offset: int
    items: List[MediaItem]


class DeviceInfo(BaseModel):
    """Device information."""
    id: int
    device_id: str
    name: Optional[str]
    firmware_version: Optional[str]
    last_seen: Optional[str]
    created_at: str
    stats: dict


class DeviceListResponse(BaseModel):
    """Device list response."""
    ok: bool = True
    devices: List[DeviceInfo]


class DeviceDetailResponse(BaseModel):
    """Detailed device information response."""
    ok: bool = True
    device: dict


@router.get("/", response_model=MediaListResponse)
async def list_media(
    device_id: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List media items with optional filtering.

    Query parameters:
    - device_id: Filter by device
    - type: Filter by type (image/video)
    - limit: Max items to return (default 50, max 100)
    - offset: Pagination offset
    - start_date: ISO 8601 datetime string (filter media captured after this date)
    - end_date: ISO 8601 datetime string (filter media captured before this date)
    - search: String to search in ai_caption and ai_tags fields
    """
    # Validate and cap limit
    limit = min(limit, 100)

    # Build query
    query = db.query(Media)

    if device_id:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if device:
            query = query.filter(Media.device_id == device.id)
        else:
            # No such device
            return MediaListResponse(
                ok=True,
                total=0,
                limit=limit,
                offset=offset,
                items=[]
            )

    if type:
        if type in ["image", "video"]:
            query = query.filter(Media.type == MediaType(type))

    # Date range filtering
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(Media.captured_at >= start_dt)
        except ValueError:
            # Invalid date format, ignore
            pass

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(Media.captured_at <= end_dt)
        except ValueError:
            # Invalid date format, ignore
            pass

    # Search in ai_caption and ai_tags_json
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Media.ai_caption.ilike(search_pattern),
                Media.ai_tags_json.ilike(search_pattern)
            )
        )

    # Get total count
    total = query.count()

    # Get items (newest first)
    items = query.order_by(desc(Media.captured_at)).limit(limit).offset(offset).all()

    # Convert to response models
    response_items = []
    for item in items:
        device = db.query(Device).filter(Device.id == item.device_id).first()

        # Parse AI tags
        ai_tags = None
        if item.ai_tags_json:
            try:
                ai_tags = json.loads(item.ai_tags_json)
            except:
                pass

        response_items.append(MediaItem(
            id=item.id,
            device_id=device.device_id if device else "unknown",
            media_id=item.media_id,
            type=item.type.value,
            captured_at=format_datetime_iso(item.captured_at, db=db),
            uploaded_at=format_datetime_iso(item.uploaded_at, db=db),
            filename=item.filename,
            thumb_filename=item.thumb_filename,
            size_bytes=item.size_bytes,
            thumb_size_bytes=item.thumb_size_bytes,
            resolution=item.resolution,
            upload_state=item.upload_state.value,
            upload_progress=item.upload_progress,
            ai_caption=item.ai_caption,
            ai_tags=ai_tags,
            ai_confidence=item.ai_confidence,
            ai_analyzed_at=format_datetime_iso(item.ai_analyzed_at, db=db) if item.ai_analyzed_at else None
        ))

    return MediaListResponse(
        ok=True,
        total=total,
        limit=limit,
        offset=offset,
        items=response_items
    )


@router.get("/{media_id}", response_model=MediaItem)
async def get_media(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get media item by ID."""
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    device = db.query(Device).filter(Device.id == media.device_id).first()

    # Parse AI tags
    ai_tags = None
    if media.ai_tags_json:
        try:
            ai_tags = json.loads(media.ai_tags_json)
        except:
            pass

    return MediaItem(
        id=media.id,
        device_id=device.device_id if device else "unknown",
        media_id=media.media_id,
        type=media.type.value,
        captured_at=format_datetime_iso(media.captured_at, db=db),
        uploaded_at=format_datetime_iso(media.uploaded_at, db=db),
        filename=media.filename,
        thumb_filename=media.thumb_filename,
        size_bytes=media.size_bytes,
        thumb_size_bytes=media.thumb_size_bytes,
        resolution=media.resolution,
        upload_state=media.upload_state.value,
        upload_progress=media.upload_progress,
        ai_caption=media.ai_caption,
        ai_tags=ai_tags,
        ai_confidence=media.ai_confidence,
        ai_analyzed_at=format_datetime_iso(media.ai_analyzed_at, db=db) if media.ai_analyzed_at else None
    )


@router.get("/{media_id}/thumb")
async def get_thumbnail(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get thumbnail image file."""
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    if not media.thumb_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available"
        )

    thumb_path = settings.storage_path / media.thumb_path

    if not thumb_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail file not found"
        )

    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        filename=media.thumb_filename
    )


@router.get("/{media_id}/file")
async def get_media_file(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get original media file."""
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    if not media.media_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not available"
        )

    media_path = settings.storage_path / media.media_path

    if not media_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )

    # Determine media type
    media_type = "image/jpeg" if media.type == MediaType.IMAGE else "video/mp4"

    return FileResponse(
        path=str(media_path),
        media_type=media_type,
        filename=media.filename
    )


@router.post("/{media_id}/reanalyze")
async def reanalyze_media(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Re-run AI analysis on a media item."""
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    # Trigger analysis
    ollama = OllamaService()

    try:
        success = await ollama.analyze_media(db, media)

        if success:
            return JSONResponse({
                "ok": True,
                "message": "Analysis completed",
                "caption": media.ai_caption,
                "tags": json.loads(media.ai_tags_json) if media.ai_tags_json else []
            })
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Analysis failed"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis error: {str(e)}"
        )


@router.get("/devices/list", response_model=DeviceListResponse)
async def list_devices(db: Session = Depends(get_db)):
    """List all registered devices."""
    devices = db.query(Device).all()

    device_list = []
    for device in devices:
        # Get media stats
        media_count = db.query(Media).filter(Media.device_id == device.id).count()
        recent_media = db.query(Media).filter(
            Media.device_id == device.id
        ).order_by(desc(Media.captured_at)).first()

        device_list.append(DeviceInfo(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            firmware_version=device.firmware_version,
            last_seen=format_datetime_iso(device.last_seen, db=db) if device.last_seen else None,
            created_at=format_datetime_iso(device.created_at, db=db),
            stats={
                "total_media": media_count,
                "last_capture": format_datetime_iso(recent_media.captured_at, db=db) if recent_media else None,
                "sd_free_mb": device.sd_free_mb,
                "uptime_seconds": device.uptime_seconds
            }
        ))

    return DeviceListResponse(
        ok=True,
        devices=device_list
    )


@router.get("/devices/{device_id}", response_model=DeviceDetailResponse)
async def get_device_details(
    device_id: str,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific device."""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    # Get comprehensive media stats
    total_media = db.query(Media).filter(Media.device_id == device.id).count()
    completed_media = db.query(Media).filter(
        Media.device_id == device.id,
        Media.upload_state == UploadState.COMPLETED
    ).count()
    pending_media = db.query(Media).filter(
        Media.device_id == device.id,
        Media.upload_state == UploadState.PENDING
    ).count()
    uploading_media = db.query(Media).filter(
        Media.device_id == device.id,
        Media.upload_state == UploadState.UPLOADING
    ).count()
    
    # Calculate total storage used by completed media
    completed_media_items = db.query(Media).filter(
        Media.device_id == device.id,
        Media.upload_state == UploadState.COMPLETED
    ).all()
    total_storage_bytes = sum(item.size_bytes or 0 for item in completed_media_items)
    total_storage_mb = total_storage_bytes / (1024 * 1024)
    
    # Get recent media
    recent_media = db.query(Media).filter(
        Media.device_id == device.id
    ).order_by(desc(Media.captured_at)).limit(5).all()
    
    # Get active upload sessions
    from app.models import UploadSession
    active_sessions = db.query(UploadSession).filter(
        UploadSession.device_id == device.id,
        UploadSession.completed == False
    ).count()
    
    # Calculate SD card usage percentage (if we have free space info)
    sd_usage_percent = None
    if device.sd_free_mb is not None:
        # Assume typical SD card sizes - we'll use a reasonable default
        # In production, you might want to store total SD size
        # For now, estimate based on free space (assume 32GB card if free > 1000MB, else 16GB)
        estimated_total_mb = 32000 if device.sd_free_mb > 1000 else 16000
        sd_used_mb = estimated_total_mb - device.sd_free_mb
        sd_usage_percent = (sd_used_mb / estimated_total_mb) * 100
    
    # Format uptime
    uptime_formatted = None
    if device.uptime_seconds:
        days = device.uptime_seconds // 86400
        hours = (device.uptime_seconds % 86400) // 3600
        minutes = (device.uptime_seconds % 3600) // 60
        uptime_formatted = f"{days}d {hours}h {minutes}m"
    
    # Determine connection status
    is_connected = False
    if device.last_seen:
        from datetime import datetime, timezone
        time_diff = (datetime.now(timezone.utc) - device.last_seen).total_seconds()
        is_connected = time_diff < 300  # Connected if seen within 5 minutes
    
    return DeviceDetailResponse(
        ok=True,
        device={
            "id": device.id,
            "device_id": device.device_id,
            "name": device.name or "Unnamed Device",
            "firmware_version": device.firmware_version,
            "created_at": format_datetime_iso(device.created_at, db=db),
            "last_seen": format_datetime_iso(device.last_seen, db=db) if device.last_seen else None,
            "is_connected": is_connected,
            "storage": {
                "sd_free_mb": device.sd_free_mb,
                "sd_usage_percent": round(sd_usage_percent, 1) if sd_usage_percent else None,
                "backend_storage_mb": round(total_storage_mb, 2),
                "backend_storage_bytes": total_storage_bytes
            },
            "stats": {
                "uptime_seconds": device.uptime_seconds,
                "uptime_formatted": uptime_formatted,
                "capture_count": device.capture_count,
                "total_media": total_media,
                "completed_media": completed_media,
                "pending_media": pending_media,
                "uploading_media": uploading_media,
                "active_upload_sessions": active_sessions
            },
            "recent_media": [
                {
                    "id": item.id,
                    "media_id": item.media_id,
                    "captured_at": format_datetime_iso(item.captured_at, db=db),
                    "upload_state": item.upload_state.value
                }
                for item in recent_media
            ]
        }
    )

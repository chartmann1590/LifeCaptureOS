"""Device API endpoints for ESP32-CAM uploads."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
from pathlib import Path
from PIL import Image  # Added for server-side thumbnail generation

from app.database import get_db
from app.models import Device, UploadPhase, MediaType, Media, UploadState
from app.auth import get_current_device
from app.upload_service import UploadService
from app.ollama_service import OllamaService
from app.config import settings
from app.timezone_utils import format_datetime_iso
from app.media_utils import resolve_captured_at

router = APIRouter(prefix="/device", tags=["device"])
logger = logging.getLogger(__name__)


async def run_analysis_task(media_id: int):
    """Background task to run analysis with its own DB session."""
    from app.database import SessionLocal
    from app.models import Media
    
    db = SessionLocal()
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if media:
            ollama = OllamaService()
            await ollama.analyze_media(db, media)
    except Exception as e:
        logger.error(f"Background analysis failed for media {media_id}: {e}")
    finally:
        db.close()



class PingRequest(BaseModel):
    """Device ping request."""
    device_id: str
    firmware_version: Optional[str] = None
    status: Optional[dict] = None


class PingResponse(BaseModel):
    """Ping response."""
    ok: bool = True
    server_time: int
    device: dict


class InitiateUploadRequest(BaseModel):
    """Request to initiate upload session."""
    device_id: str
    media_id: str
    type: str = Field(..., pattern="^(image|video)$")
    captured_at: int  # Unix timestamp
    phase: str = Field(..., pattern="^(metadata|media)$")
    metadata: Optional[dict] = None
    expected_size: int = Field(..., gt=0)


class InitiateUploadResponse(BaseModel):
    """Initiate upload response."""
    ok: bool = True
    upload_id: str
    session: dict
    resume_supported: bool = True


class UploadStatusResponse(BaseModel):
    """Upload status response."""
    ok: bool = True
    upload_id: str
    device_id: str
    media_id: str
    phase: str
    received_bytes: int
    expected_size: int
    progress: float
    next_offset: int
    created_at: str
    updated_at: Optional[str]
    expires_at: str


class CompleteUploadRequest(BaseModel):
    """Complete upload request."""
    sha256: Optional[str] = None
    crc32: Optional[str] = None


class CompleteUploadResponse(BaseModel):
    """Complete upload response."""
    ok: bool = True
    phase: str
    status: str
    media_id: str
    media_record_id: Optional[int] = None
    next_step: Optional[str] = None
    message: Optional[str] = None
    analysis_queued: Optional[bool] = None
    storage: Optional[dict] = None


@router.post("/ping", response_model=PingResponse)
async def ping(
    request: PingRequest,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Health check and device status update."""
    # Update device last_seen and stats
    device.last_seen = datetime.now(timezone.utc)

    if request.firmware_version:
        device.firmware_version = request.firmware_version

    if request.status:
        device.uptime_seconds = request.status.get("uptime_seconds")
        device.sd_free_mb = request.status.get("sd_free_mb")
        device.capture_count = request.status.get("capture_count")

    db.commit()

    logger.debug(
        f"Device ping: {device.device_id} ({device.name or 'Unnamed'}), "
        f"firmware={request.firmware_version or 'unknown'}, "
        f"uptime={request.status.get('uptime_seconds') if request.status else None}s"
    )

    return PingResponse(
        ok=True,
        server_time=int(datetime.now(timezone.utc).timestamp()),
        device={
            "id": device.device_id,
            "name": device.name or "Unnamed Device",
            "registered_at": int(device.created_at.timestamp())
        }
    )


@router.post("/media/initiate", response_model=InitiateUploadResponse, status_code=status.HTTP_201_CREATED)
async def initiate_upload(
    request: InitiateUploadRequest,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Initiate a new upload session."""
    # Validate device_id matches authenticated device
    if request.device_id != device.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="device_id mismatch"
        )

    # Validate size limits
    max_size = (
        settings.max_image_size_bytes if request.type == "image"
        else settings.max_video_size_bytes
    )

    if request.phase == "metadata":
        max_size = settings.max_thumbnail_size_bytes * 2  # Metadata + thumbnail

    if request.expected_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {max_size} bytes"
        )

    # Check for existing upload sessions for this media_id
    upload_service = UploadService(db)
    from app.models import UploadSession
    existing = db.query(UploadSession).filter(
        UploadSession.device_id == device.id,
        UploadSession.media_id == request.media_id,
        UploadSession.phase == request.phase,
        UploadSession.completed == False
    ).first()

    if existing:
        # Return existing session for resume
        logger.info(
            f"Upload resumed: device={device.device_id}, media_id={request.media_id}, "
            f"upload_id={existing.upload_id}, progress={existing.received_bytes}/{existing.expected_size} bytes"
        )
        return InitiateUploadResponse(
            ok=True,
            upload_id=existing.upload_id,
            session={
                "chunk_size": settings.chunk_size_bytes,
                "received_bytes": existing.received_bytes,
                "expected_size": existing.expected_size,
                "expires_at": int(existing.expires_at.timestamp())
            },
            resume_supported=True
        )

    # Create new session
    metadata = dict(request.metadata or {})
    metadata.setdefault("captured_at", request.captured_at)
    metadata.setdefault("type", request.type)
    captured_at = resolve_captured_at(request.captured_at, request.media_id)
    session = upload_service.initiate_session(
        device=device,
        media_id=request.media_id,
        media_type=MediaType(request.type),
        captured_at=captured_at,
        phase=UploadPhase(request.phase),
        expected_size=request.expected_size,
        metadata=metadata
    )

    logger.info(
        f"Upload initiated: device={device.device_id}, media_id={request.media_id}, "
        f"type={request.type}, phase={request.phase}, size={request.expected_size} bytes, "
        f"upload_id={session.upload_id}"
    )

    return InitiateUploadResponse(
        ok=True,
        upload_id=session.upload_id,
        session={
            "chunk_size": settings.chunk_size_bytes,
            "received_bytes": 0,
            "expected_size": request.expected_size,
            "expires_at": int(session.expires_at.timestamp())
        },
        resume_supported=True
    )


@router.put("/media/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    request: Request,
    content_range: Optional[str] = Header(None),
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Upload a chunk of data."""
    upload_service = UploadService(db)

    # Get session
    session = upload_service.get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )

    # Verify device owns session
    if session.device_id != device.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your upload session"
        )

    # Parse Content-Range header
    # Format: bytes <start>-<end>/<total>
    if not content_range:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Range header required"
        )

    try:
        range_part = content_range.replace("bytes ", "")
        range_data, total = range_part.split("/")
        start, end = map(int, range_data.split("-"))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Content-Range header"
        )

    # Read chunk data
    chunk_data = await request.body()
    chunk_size = len(chunk_data)

    # Verify chunk size matches range
    expected_size = end - start + 1
    if chunk_size != expected_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chunk size mismatch: expected {expected_size}, got {chunk_size}"
        )

    # Write chunk
    success, received_bytes = upload_service.write_chunk(session, start, chunk_data)

    if not success:
        logger.warning(
            f"Upload chunk offset mismatch: device={device.device_id}, upload_id={upload_id}, "     
            f"expected={received_bytes}, got={start}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Offset mismatch. Expected offset: {received_bytes}"
        )

    # Calculate progress
    progress = (received_bytes / session.expected_size * 100) if session.expected_size else 0       

    logger.debug(
        f"Upload chunk received: device={device.device_id}, upload_id={upload_id}, "
        f"progress={progress:.1f}% ({received_bytes}/{session.expected_size} bytes)"
    )

    return JSONResponse({
        "ok": True,
        "received_bytes": received_bytes,
        "expected_size": session.expected_size,
        "progress": round(progress, 2),
        "next_offset": received_bytes
    })


@router.get("/media/{upload_id}/status", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: str,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Get upload session status."""
    upload_service = UploadService(db)

    session = upload_service.get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )

    # Verify device owns session
    if session.device_id != device.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your upload session"
        )

    progress = (session.received_bytes / session.expected_size * 100) if session.expected_size else 0

    return UploadStatusResponse(
        ok=True,
        upload_id=session.upload_id,
        device_id=device.device_id,
        media_id=session.media_id,
        phase=session.phase.value,
        received_bytes=session.received_bytes,
        expected_size=session.expected_size or 0,
        progress=round(progress, 2),
        next_offset=session.received_bytes,
        created_at=format_datetime_iso(session.created_at, db=db),
        updated_at=format_datetime_iso(session.updated_at, db=db) if session.updated_at else None,  
        expires_at=format_datetime_iso(session.expires_at, db=db)
    )


@router.post("/media/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_upload(
    upload_id: str,
    request: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Complete upload session and trigger processing."""
    # Update last_seen
    device.last_seen = datetime.now(timezone.utc)

    upload_service = UploadService(db)

    session = upload_service.get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )

    # Verify device owns session
    if session.device_id != device.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your upload session"
        )

    # Complete session
    success, error = upload_service.complete_session(session, request.sha256)

    if not success:
        logger.error(
            f"Upload completion failed: device={device.device_id}, upload_id={upload_id}, "
            f"media_id={session.media_id}, error={error}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Upload completion failed"
        )

    # Prepare response based on phase
    if session.phase == UploadPhase.METADATA:
        logger.info(
            f"Upload completed (metadata phase): device={device.device_id}, "
            f"media_id={session.media_id}, upload_id={upload_id}, size={session.received_bytes} bytes"
        )
        return CompleteUploadResponse(
            ok=True,
            phase="metadata",
            status="completed",
            media_id=session.media_id,
            next_step="upload_media",
            message="Metadata and thumbnail received. Now upload original media."
        )
    else:
        # Media phase - trigger AI analysis
        # Get media record
        media = db.query(Media).filter(
            Media.device_id == device.id,
            Media.media_id == session.media_id
        ).first()

        logger.info(
            f"Upload completed (media phase): device={device.device_id}, "
            f"media_id={session.media_id}, upload_id={upload_id}, "
            f"size={session.received_bytes} bytes, media_record_id={media.id if media else None}"   
        )

        # Queue AI analysis (async)
        if media:
            background_tasks.add_task(run_analysis_task, media.id)

        return CompleteUploadResponse(
            ok=True,
            phase="media",
            status="completed",
            media_id=session.media_id,
            media_record_id=media.id if media else None,
            analysis_queued=True,
            storage={
                "media_path": media.media_path if media else None,
                "thumb_path": media.thumb_path if media else None,
                "size_bytes": media.size_bytes if media else None
            }
        )


@router.delete("/media/{upload_id}")
async def abort_upload(
    upload_id: str,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Abort and clean up upload session."""
    upload_service = UploadService(db)

    session = upload_service.get_session(upload_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )

    # Verify device owns session
    if session.device_id != device.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your upload session"
        )

    upload_service.abort_session(session)

    return JSONResponse({
        "ok": True,
        "message": "Upload session aborted and cleaned up"
    })


# Import UploadSession here to avoid circular import
from app.models import UploadSession

@router.post("/upload/image")
async def upload_image_simple(
    request: Request,
    background_tasks: BackgroundTasks,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    """Simple single-request upload for MVP firmware."""
    # Update last_seen
    device.last_seen = datetime.now(timezone.utc)
    
    # 1. Get/Generate Media ID
    media_id = request.headers.get("X-Media-ID")
    if not media_id:
        media_id = f"IMG_{uuid.uuid4().hex[:8]}"

    # 2. Read Body
    body = await request.body()
    size = len(body)
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty body")

    captured_at = resolve_captured_at(
        request.headers.get("X-Captured-At"),
        media_id
    )

    # 3. Setup Paths
    filename = f"{media_id}.jpg"
    thumb_filename = f"THM_{media_id}.jpg"

    date_str = captured_at.strftime("%Y/%m/%d")
    
    save_dir = settings.media_path / date_str
    save_dir.mkdir(parents=True, exist_ok=True)
    
    thumb_dir = settings.thumbs_path / date_str
    thumb_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = save_dir / filename
    thumb_path = thumb_dir / thumb_filename

    # 4. Save Main File
    with open(file_path, "wb") as f:
        f.write(body)
        
    # 5. Generate Thumbnail (Server-Side)
    try:
        with Image.open(file_path) as img:
            # Convert to RGB if needed (e.g. if RGBA)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail (320x240 max)
            img.thumbnail((320, 240))
            img.save(thumb_path, "JPEG", quality=70)
            
            thumb_size = thumb_path.stat().st_size
            has_thumb = True
    except Exception as e:
        logger.error(f"Thumbnail generation failed for {media_id}: {e}")
        has_thumb = False
        thumb_size = 0

    # 6. Create DB Entry
    media_item = Media(
        device_id=device.id,
        media_id=media_id,
        type=MediaType.IMAGE,
        captured_at=captured_at,
        uploaded_at=datetime.now(timezone.utc),
        filename=filename,
        media_path=str(file_path.relative_to(settings.storage_path)),
        
        # Add thumbnail info if successful
        thumb_filename=thumb_filename if has_thumb else None,
        thumb_path=str(thumb_path.relative_to(settings.storage_path)) if has_thumb else None,
        thumb_size_bytes=thumb_size if has_thumb else 0,
        
        size_bytes=size,
        upload_state=UploadState.COMPLETED,
        upload_progress=100.0,
        resolution="1600x1200"
    )
    db.add(media_item)
    db.commit()
    db.refresh(media_item)
    
    # 7. Trigger AI Analysis
    try:
        background_tasks.add_task(run_analysis_task, media_item.id)
    except Exception as e:
        logger.warning(f"Failed to queue AI analysis: {e}")
    
    return JSONResponse({
        "ok": True, 
        "media_id": media_id,
        "media_record_id": media_item.id,
        "thumbnail_generated": has_thumb
    })

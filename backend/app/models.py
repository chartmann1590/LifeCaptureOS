"""SQLAlchemy database models."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.database import Base


class SystemSettings(Base):
    """System-wide settings stored as key-value pairs."""
    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UploadState(str, enum.Enum):
    """Media upload states."""
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaType(str, enum.Enum):
    """Media types."""
    IMAGE = "image"
    VIDEO = "video"


class UploadPhase(str, enum.Enum):
    """Upload session phases."""
    METADATA = "metadata"
    MEDIA = "media"


class Device(Base):
    """Registered devices (ESP32-CAM units)."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=True)
    token_hash = Column(String(128), nullable=False)  # Hashed device token

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=True)

    # Stats (updated from ping)
    firmware_version = Column(String(32), nullable=True)
    uptime_seconds = Column(Integer, nullable=True)
    sd_free_mb = Column(Integer, nullable=True)
    capture_count = Column(Integer, nullable=True)

    # Relationships
    media = relationship("Media", back_populates="device")
    upload_sessions = relationship("UploadSession", back_populates="device")


class Media(Base):
    """Media items (photos/videos) uploaded from devices."""
    __tablename__ = "media"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    # Media identification
    media_id = Column(String(128), nullable=False, index=True)  # From ESP32
    type = Column(Enum(MediaType), nullable=False)

    # Timestamps
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # File info
    filename = Column(String(256), nullable=False)
    thumb_filename = Column(String(256), nullable=True)
    media_path = Column(String(512), nullable=True)  # Relative to storage_dir
    thumb_path = Column(String(512), nullable=True)

    size_bytes = Column(Integer, nullable=True)
    thumb_size_bytes = Column(Integer, nullable=True)

    # Metadata
    resolution = Column(String(32), nullable=True)  # e.g., "1600x1200"
    quality = Column(Integer, nullable=True)  # JPEG quality 1-100
    sha256 = Column(String(64), nullable=True)

    # Upload state
    upload_state = Column(Enum(UploadState), default=UploadState.PENDING, index=True)
    upload_progress = Column(Float, default=0.0)  # 0-100

    # AI analysis
    ai_caption = Column(Text, nullable=True)
    ai_tags_json = Column(Text, nullable=True)  # JSON array of tags
    ai_confidence = Column(Float, nullable=True)
    ai_analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    device = relationship("Device", back_populates="media")


class UploadSession(Base):
    """Resumable upload sessions."""
    __tablename__ = "upload_sessions"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(String(64), unique=True, nullable=False, index=True)

    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    media_id = Column(String(128), nullable=False, index=True)

    phase = Column(Enum(UploadPhase), nullable=False)

    # Upload progress
    target_path = Column(String(512), nullable=False)  # Where to save
    received_bytes = Column(Integer, default=0)
    expected_size = Column(Integer, nullable=True)

    # Session lifecycle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed = Column(Boolean, default=False)

    # Metadata (for metadata phase)
    metadata_json = Column(Text, nullable=True)

    # Relationships
    device = relationship("Device", back_populates="upload_sessions")


class DailySummary(Base):
    """Daily AI summary videos."""
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD format
    
    # Video file info
    video_path = Column(String(512), nullable=False)  # Relative to storage_dir
    
    # Content info
    memory_ids = Column(Text, nullable=False)  # JSON array of media IDs
    music_track_id = Column(String(128), nullable=True)
    music_track_title = Column(String(256), nullable=True)
    day_summary = Column(Text, nullable=True)  # AI-generated summary text
    
    # Metadata
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # 30 days from generation
    duration_seconds = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)


class DailySummaryJobStatus(str, enum.Enum):
    """Daily summary generation job statuses."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DailySummaryJob(Base):
    """Background job tracking for daily summary generation."""
    __tablename__ = "daily_summary_jobs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD format
    status = Column(Enum(DailySummaryJobStatus), nullable=False, index=True)
    allow_duplicate = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    summary_id = Column(Integer, ForeignKey("daily_summaries.id"), nullable=True, index=True)

    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    summary = relationship("DailySummary")

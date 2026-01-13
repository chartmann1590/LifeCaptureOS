"""Upload session management and resumable upload logic."""
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Device, Media, UploadSession, UploadPhase, UploadState, MediaType
from app.config import settings
from app.media_utils import resolve_captured_at


class UploadService:
    """Service for managing resumable uploads."""

    def __init__(self, db: Session):
        self.db = db

    def initiate_session(
        self,
        device: Device,
        media_id: str,
        media_type: MediaType,
        captured_at: datetime,
        phase: UploadPhase,
        expected_size: int,
        metadata: Optional[dict] = None
    ) -> UploadSession:
        """Create a new upload session."""

        # Generate unique upload ID
        import secrets
        upload_id = f"upload_{secrets.token_hex(16)}"

        # Determine target path based on phase and date
        date_path = captured_at.strftime("%Y/%m/%d")

        if phase == UploadPhase.METADATA:
            # Metadata phase: save to temp location
            target_path = settings.storage_path / "temp" / f"{upload_id}.metadata"
        else:
            # Media phase: save to organized directory
            if media_type == MediaType.IMAGE:
                base_path = settings.media_path / device.device_id / date_path
                filename = f"{media_id}.jpg"
            else:
                base_path = settings.media_path / device.device_id / date_path
                filename = f"{media_id}.mp4"

            base_path.mkdir(parents=True, exist_ok=True)
            target_path = base_path / filename

        # Create session
        session = UploadSession(
            upload_id=upload_id,
            device_id=device.id,
            media_id=media_id,
            phase=phase,
            target_path=str(target_path),
            received_bytes=0,
            expected_size=expected_size,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            metadata_json=json.dumps(metadata) if metadata else None
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        # Ensure parent directory exists
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)

        return session

    def get_session(self, upload_id: str) -> Optional[UploadSession]:
        """Get upload session by ID."""
        return self.db.query(UploadSession).filter(
            UploadSession.upload_id == upload_id
        ).first()

    def write_chunk(
        self,
        session: UploadSession,
        offset: int,
        data: bytes
    ) -> Tuple[bool, int]:
        """
        Write chunk to upload session file.

        Returns:
            (success, bytes_written)
        """
        # Validate offset
        if offset != session.received_bytes:
            # Offset mismatch - client should resume from received_bytes
            return False, session.received_bytes

        # Write to file
        target_path = Path(session.target_path)

        mode = "ab" if offset > 0 else "wb"
        with open(target_path, mode) as f:
            if offset > 0:
                # Verify file size matches expected offset
                f.seek(0, os.SEEK_END)
                current_size = f.tell()
                if current_size != offset:
                    # File size mismatch - corruption or tampering
                    return False, current_size

            bytes_written = f.write(data)

        # Update session
        session.received_bytes += bytes_written
        session.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        return True, session.received_bytes

    def complete_session(
        self,
        session: UploadSession,
        sha256: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Complete upload session and finalize file.

        Returns:
            (success, error_message)
        """
        target_path = Path(session.target_path)

        # Verify file exists and size matches
        if not target_path.exists():
            return False, "File not found"

        file_size = target_path.stat().st_size
        if session.expected_size and file_size != session.expected_size:
            return False, f"Size mismatch: expected {session.expected_size}, got {file_size}"

        # Verify SHA256 if provided
        if sha256:
            import hashlib
            computed_hash = hashlib.sha256()
            with open(target_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    computed_hash.update(chunk)

            if computed_hash.hexdigest() != sha256:
                return False, "SHA256 checksum mismatch"

        # Mark session as completed
        session.completed = True
        session.updated_at = datetime.utcnow()
        self.db.commit()

        # Handle based on phase
        if session.phase == UploadPhase.METADATA:
            # Extract metadata and thumbnail
            return self._process_metadata_upload(session)
        else:
            # Process media upload
            return self._process_media_upload(session, sha256)

    def _process_metadata_upload(self, session: UploadSession) -> Tuple[bool, Optional[str]]:
        """Process completed metadata+thumbnail upload."""
        # For metadata phase, we expect:
        # - First N bytes: JSON metadata
        # - Remaining bytes: Thumbnail JPEG

        target_path = Path(session.target_path)

        try:
            # Read file
            with open(target_path, "rb") as f:
                content = f.read()

            # Parse metadata from session
            if session.metadata_json:
                metadata = json.loads(session.metadata_json)
            else:
                # Try to extract from file (first chunk should be JSON)
                # This is a simplified approach; production might need better parsing
                metadata = {}

            # Extract thumbnail (assume rest of file is thumbnail)
            # In real implementation, metadata would specify thumbnail_size
            thumb_size = metadata.get("thumbnail_size", len(content))

            if "thumbnail_size" in metadata:
                # Extract thumbnail from file
                metadata_size = len(content) - thumb_size
                thumbnail_data = content[metadata_size:]
            else:
                # Whole file is thumbnail (metadata was in session.metadata_json)
                thumbnail_data = content

            # Save thumbnail to proper location
            device = self.db.query(Device).filter(Device.id == session.device_id).first()
            captured_at = resolve_captured_at(
                metadata.get("captured_at"),
                session.media_id,
                session.created_at
            )
            date_path = captured_at.strftime("%Y/%m/%d")

            thumb_dir = settings.thumbs_path / device.device_id / date_path
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_filename = f"THM_{session.media_id}.jpg"
            thumb_path = thumb_dir / thumb_filename

            with open(thumb_path, "wb") as f:
                f.write(thumbnail_data)

            # Create or update media record
            media = self.db.query(Media).filter(
                Media.device_id == device.id,
                Media.media_id == session.media_id
            ).first()

            if not media:
                media = Media(
                    device_id=device.id,
                    media_id=session.media_id,
                    type=MediaType(metadata.get("type", "image")),
                    captured_at=captured_at,
                    filename=metadata.get("filename", f"{session.media_id}.jpg"),
                    thumb_filename=thumb_filename,
                    thumb_path=str(thumb_path.relative_to(settings.storage_path)),
                    resolution=metadata.get("resolution"),
                    quality=metadata.get("quality"),
                    size_bytes=metadata.get("size_bytes"),
                    thumb_size_bytes=len(thumbnail_data),
                    upload_state=UploadState.PENDING
                )
                self.db.add(media)
            else:
                # Update existing record
                media.thumb_filename = thumb_filename
                media.thumb_path = str(thumb_path.relative_to(settings.storage_path))
                media.thumb_size_bytes = len(thumbnail_data)

            self.db.commit()

            # Clean up temp file
            target_path.unlink(missing_ok=True)

            return True, None

        except Exception as e:
            return False, f"Metadata processing error: {str(e)}"

    def _process_media_upload(self, session: UploadSession, sha256: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Process completed media file upload."""
        device = self.db.query(Device).filter(Device.id == session.device_id).first()

        # Find or create media record
        media = self.db.query(Media).filter(
            Media.device_id == device.id,
            Media.media_id == session.media_id
        ).first()

        if not media:
            metadata = {}
            if session.metadata_json:
                try:
                    metadata = json.loads(session.metadata_json)
                except json.JSONDecodeError:
                    metadata = {}
            captured_at = resolve_captured_at(
                metadata.get("captured_at"),
                session.media_id,
                session.created_at
            )
            media_type = MediaType.IMAGE
            if isinstance(metadata.get("type"), str):
                try:
                    media_type = MediaType(metadata["type"])
                except ValueError:
                    pass
            # Create new record if metadata phase was skipped
            media = Media(
                device_id=device.id,
                media_id=session.media_id,
                type=media_type,
                captured_at=captured_at,
                filename=Path(session.target_path).name,
                upload_state=UploadState.UPLOADING
            )
            self.db.add(media)

        # Update media record
        media.media_path = str(Path(session.target_path).relative_to(settings.storage_path))
        media.size_bytes = session.received_bytes
        media.sha256 = sha256
        media.upload_state = UploadState.COMPLETED
        media.upload_progress = 100.0

        self.db.commit()
        self.db.refresh(media)

        return True, None

    def abort_session(self, session: UploadSession) -> bool:
        """Abort and clean up upload session."""
        target_path = Path(session.target_path)

        # Delete partial file
        if target_path.exists():
            target_path.unlink()

        # Delete session
        self.db.delete(session)
        self.db.commit()

        return True

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired upload sessions. Returns count of cleaned up sessions."""
        now = datetime.now(timezone.utc)
        expired = self.db.query(UploadSession).filter(
            UploadSession.expires_at < now,
            UploadSession.completed == False
        ).all()

        count = 0
        for session in expired:
            self.abort_session(session)
            count += 1

        return count

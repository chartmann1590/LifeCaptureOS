"""Application configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path
from typing import Optional
import os

# Fix corrupted timezone environment variable if present (UTF-16 encoding issue on Windows)
if "timezone" in os.environ:
    tz_value = os.environ.get("timezone", "")
    if "\x00" in tz_value or not isinstance(tz_value, str) or not tz_value.strip():
        # Remove corrupted timezone environment variable
        # It will use the default "UTC" from the Settings class
        del os.environ["timezone"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Storage
    storage_dir: str = "./data"
    db_path: str = "./data/app.db"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_vision_model: str = "moondream"
    ollama_chat_model: str = "llama3"  # Text model for chat
    ollama_timeout: int = 60
    ollama_chat_timeout: int = 30  # Timeout for chat requests

    # Security
    device_shared_secret: str = os.getenv("DEVICE_SHARED_SECRET", "change-this-in-production")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Upload limits
    max_image_size_mb: int = 10
    max_video_size_mb: int = 100
    max_thumbnail_size_kb: int = 100
    chunk_size_bytes: int = 65536

    # Rate limiting
    max_requests_per_minute: int = 100
    max_upload_sessions_per_device: int = 5

    # Timezone
    timezone: str = "UTC"  # Default timezone, can be overridden via web UI
    
    # Video generation
    video_storage_path: Optional[str] = None  # Path for storing generated videos (defaults to storage_dir/videos)
    video_retention_days: int = 30  # Days to keep videos before expiration
    summary_generation_time: str = "05:00"  # Time to generate summaries (HH:MM format)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    @field_validator("timezone", mode="before")
    @classmethod
    def clean_timezone(cls, v):
        """Clean timezone value from encoding issues."""
        if not v:
            return "UTC"
        
        # Convert to string if not already
        if not isinstance(v, str):
            v = str(v)
        
        # Remove null bytes (UTF-16 encoding artifacts)
        if "\x00" in v:
            # Try to decode as UTF-16LE if it looks like UTF-16
            try:
                # Remove null bytes and try to reconstruct
                cleaned = v.replace("\x00", "")
                # If it had null bytes between characters, try UTF-16 decode
                if len(v) % 2 == 0 and len(v) > len(cleaned):
                    try:
                        # Try UTF-16LE decode
                        decoded = v.encode('latin1').decode('utf-16le', errors='ignore')
                        if decoded and decoded.strip():
                            return decoded.strip()
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        pass
                # Fallback: just remove null bytes
                return cleaned.strip() if cleaned.strip() else "UTC"
            except Exception:
                # If anything fails, remove null bytes and return
                return v.replace("\x00", "").strip() or "UTC"
        
        return v.strip() if v.strip() else "UTC"

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir)

    @property
    def media_path(self) -> Path:
        return self.storage_path / "media"

    @property
    def thumbs_path(self) -> Path:
        return self.storage_path / "thumbs"

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def max_video_size_bytes(self) -> int:
        return self.max_video_size_mb * 1024 * 1024

    @property
    def max_thumbnail_size_bytes(self) -> int:
        return self.max_thumbnail_size_kb * 1024
    
    @property
    def videos_path(self) -> Path:
        """Path for storing generated videos."""
        if self.video_storage_path:
            return Path(self.video_storage_path)
        return self.storage_path / "videos"


settings = Settings()

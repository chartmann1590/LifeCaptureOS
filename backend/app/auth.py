"""Authentication utilities for device tokens."""
import hashlib
import secrets
import logging
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.models import Device
from app.database import get_db

security = HTTPBearer()
logger = logging.getLogger(__name__)


def hash_token(token: str) -> str:
    """Hash a device token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_device_token() -> str:
    """Generate a new device token."""
    return f"dev_tok_{secrets.token_urlsafe(32)}"


def verify_device_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> Device:
    """
    Verify device token and return device.

    This is a dependency function. Use with FastAPI Depends().
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )

    token = credentials.credentials
    token_hash = hash_token(token)

    device = db.query(Device).filter(Device.token_hash == token_hash).first()

    if not device:
        logger.warning(f"Failed device authentication attempt with invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token"
        )

    logger.info(f"Device connected: {device.device_id} ({device.name or 'Unnamed'})")
    return device


async def get_current_device(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> Device:
    """
    FastAPI dependency to get current authenticated device.

    Usage:
        @app.get("/protected")
        def protected(device: Device = Depends(get_current_device)):
            ...
    """
    return verify_device_token(credentials, db)

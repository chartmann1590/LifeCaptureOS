"""Settings API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import SystemSettings
from app.timezone_utils import validate_timezone, get_timezone

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TimezoneResponse(BaseModel):
    """Timezone setting response."""
    ok: bool = True
    timezone: str


class TimezoneUpdateRequest(BaseModel):
    """Timezone update request."""
    timezone: str


class DailySummariesEnabledResponse(BaseModel):
    """Daily summaries enabled setting response."""
    ok: bool = True
    enabled: bool


class DailySummariesEnabledUpdateRequest(BaseModel):
    """Daily summaries enabled update request."""
    enabled: bool


@router.get("/timezone", response_model=TimezoneResponse)
async def get_timezone_setting(db: Session = Depends(get_db)):
    """Get current timezone setting."""
    timezone_str = get_timezone(db)
    return TimezoneResponse(ok=True, timezone=timezone_str)


@router.put("/timezone", response_model=TimezoneResponse)
async def update_timezone_setting(
    request: TimezoneUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update timezone setting."""
    # Validate timezone string
    if not validate_timezone(request.timezone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {request.timezone}. Must be a valid IANA timezone name (e.g., 'America/New_York', 'Europe/London', 'UTC')."
        )
    
    # Get or create timezone setting
    timezone_setting = db.query(SystemSettings).filter(
        SystemSettings.key == "timezone"
    ).first()
    
    if timezone_setting:
        timezone_setting.value = request.timezone
    else:
        timezone_setting = SystemSettings(
            key="timezone",
            value=request.timezone
        )
        db.add(timezone_setting)
    
    db.commit()
    db.refresh(timezone_setting)
    
    return TimezoneResponse(ok=True, timezone=timezone_setting.value)


@router.get("/daily-summaries-enabled", response_model=DailySummariesEnabledResponse)
async def get_daily_summaries_enabled(db: Session = Depends(get_db)):
    """Get current daily summaries enabled setting."""
    setting = db.query(SystemSettings).filter(
        SystemSettings.key == "daily_summaries_enabled"
    ).first()
    
    # Default to True if not set
    if setting:
        enabled = setting.value.lower() == "true"
    else:
        enabled = True
    
    return DailySummariesEnabledResponse(ok=True, enabled=enabled)


@router.put("/daily-summaries-enabled", response_model=DailySummariesEnabledResponse)
async def update_daily_summaries_enabled(
    request: DailySummariesEnabledUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update daily summaries enabled setting."""
    # Get or create setting
    setting = db.query(SystemSettings).filter(
        SystemSettings.key == "daily_summaries_enabled"
    ).first()
    
    value_str = "true" if request.enabled else "false"
    
    if setting:
        setting.value = value_str
    else:
        setting = SystemSettings(
            key="daily_summaries_enabled",
            value=value_str
        )
        db.add(setting)
    
    db.commit()
    db.refresh(setting)
    
    return DailySummariesEnabledResponse(ok=True, enabled=request.enabled)

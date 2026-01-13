"""Database setup and session management."""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path

from app.config import settings

# Ensure database directory exists
db_path = Path(settings.db_path)
db_path.parent.mkdir(parents=True, exist_ok=True)

# SQLite database URL
SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.db_path}"

# Create engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=settings.debug
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    
    # Initialize default timezone setting if not exists
    from app.models import SystemSettings
    from app.config import settings
    
    db = SessionLocal()
    try:
        timezone_setting = db.query(SystemSettings).filter(
            SystemSettings.key == "timezone"
        ).first()
        
        if not timezone_setting:
            timezone_setting = SystemSettings(
                key="timezone",
                value=settings.timezone
            )
            db.add(timezone_setting)
            db.commit()
    finally:
        db.close()

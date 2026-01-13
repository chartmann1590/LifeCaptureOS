import asyncio
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock
from datetime import date
from PIL import Image, ImageDraw
import shutil

sys.path.append(str(Path.cwd()))

from app.video_service import VideoGenerationService
from app.models import Media

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_video_gen():
    print("Setting up debug environment...")
    
    # Create temp directory
    test_dir = Path("debug_assets")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    # Mock settings
    class MockSettings:
        storage_path = test_dir
        videos_path = test_dir / "videos"
        video_retention_days = 7
        
    import app.config
    import app.video_service
    
    app.config.settings = MockSettings()
    app.video_service.settings = MockSettings()
    app.video_service.settings.storage_path.mkdir(exist_ok=True)
    app.video_service.settings.videos_path.mkdir(exist_ok=True)

    # 1. Create dummy images
    memories = []
    for i in range(5):
        img_path = test_dir / f"img_{i}.jpg"
        img = Image.new('RGB', (1920, 1080), color=(i*50, 100, 100))
        d = ImageDraw.Draw(img)
        d.text((100,100), f"Image {i}", fill="white")
        img.save(img_path)
        
        media = MagicMock(spec=Media)
        media.id = i
        media.media_path = str(img_path.name)
        media.ai_caption = f"Caption {i}"
        memories.append(media)

    # 2. Service
    service = VideoGenerationService()
    # Ensure mocked paths are used
    service.videos_path = app.video_service.settings.videos_path
    service.temp_dir = app.video_service.settings.storage_path / "temp" / "video_gen"
    service.temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Test
    print("Running _create_video...")
    target_date = date(2023, 10, 27)
    
    try:
        # We manually call the method but we also print the command that IS generated if it fails inside
        # Actually _create_video eats the error? 
        # It logs it.
        # But subprocess info is in the log.
        # We configured logging to INFO, so we should see it.
        
        video_path = await service._create_video(
            memories=memories,
            day_summary="Debug Summary",
            target_date=target_date,
            music_file=None,
            track_info={}
        )
        
        if video_path:
            print(f"SUCCESS: {video_path}")
        else:
            print("FAILURE: returned None")
            
    except Exception as e:
        print(f"CRASH: {e}")

if __name__ == "__main__":
    asyncio.run(debug_video_gen())

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from datetime import date
from PIL import Image, ImageDraw

# Add app to path
sys.path.append(str(Path.cwd()))

from app.video_service import VideoGenerationService
from app.models import Media

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_video_generation():
    print("Setting up test environment...")
    
    # Create temp directory for test assets
    test_dir = Path("test_assets")
    test_dir.mkdir(exist_ok=True)
    
    # Mock settings
    class MockSettings:
        storage_path = test_dir
        videos_path = test_dir / "videos"
        video_retention_days = 7
        
    import app.config
    import app.video_service
    
    # Patch settings in both places
    app.config.settings = MockSettings()
    app.video_service.settings = MockSettings()
    app.video_service.settings.storage_path.mkdir(exist_ok=True)
    app.video_service.settings.videos_path.mkdir(exist_ok=True)

    # 1. Create dummy images
    print("Creating dummy images...")
    memories = []
    for i in range(5):
        img_path = test_dir / f"img_{i}.jpg"
        img = Image.new('RGB', (1920, 1080), color=(i*50, 100, 100))
        d = ImageDraw.Draw(img)
        d.text((100,100), f"Image {i}", fill="white")
        img.save(img_path)
        
        media = MagicMock(spec=Media)
        media.id = i
        # The service joins storage_path / media_path. 
        # Since storage_path is "test_assets", setting media_path to "img_i.jpg" 
        # results in "test_assets/img_i.jpg" which exists.
        media.media_path = str(img_path.name)
        media.ai_caption = f"This is caption for image {i}. It describes a beautiful scene."
        memories.append(media)

    # 2. Mock Services
    print("Mocking services...")
    service = VideoGenerationService()
    # Ensure service initialized with mocked paths if it uses them in __init__
    service.videos_path = app.config.settings.videos_path
    service.temp_dir = app.config.settings.storage_path / "temp" / "video_gen"
    service.temp_dir.mkdir(parents=True, exist_ok=True)
    
    service.music_service = MagicMock()
    service.music_service.get_random_instrumental_track = AsyncMock(return_value={'track_id': '123', 'title': 'Test Track'})
    service.music_service.download_track = AsyncMock(return_value=None) # No music for simplicty
    
    service.ollama_service = MagicMock()
    service.ollama_service.chat_completion = AsyncMock(return_value="This was a wonderful day full of test images and debug logs.")

    # 3. Test _create_video directly
    print("Testing _create_video...")
    target_date = date(2023, 10, 27)
    day_summary = "This was a wonderful day full of test images."
    
    try:
        video_path = await service._create_video(
            memories=memories,
            day_summary=day_summary,
            target_date=target_date,
            music_file=None,
            track_info={'title': 'Test'}
        )
        
        if video_path and video_path.exists():
            print(f"SUCCESS: Video generated at {video_path}")
            print(f"Video size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("FAILURE: Video path returned but file not found or None returned")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        # shutil.rmtree(test_dir)
        pass

if __name__ == "__main__":
    asyncio.run(test_video_generation())

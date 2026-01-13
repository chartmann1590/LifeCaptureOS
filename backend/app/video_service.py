"""Video generation service for daily AI summary videos."""
import json
import logging
import random
import subprocess
import shutil
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont
import tempfile
import time

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import Media, DailySummary, DailySummaryJob, DailySummaryJobStatus
from app.config import settings
from app.music_service import MusicService
from app.ollama_service import OllamaService

logger = logging.getLogger(__name__)


class VideoGenerationService:
    """Service for generating daily summary videos."""
    
    def __init__(self):
        self.music_service = MusicService()
        self.ollama_service = OllamaService()
        self.videos_path = settings.videos_path
        self.videos_path.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(settings.storage_path) / "temp" / "video_gen"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def generate_daily_summary(
        self,
        target_date: date,
        job: "DailySummaryJob",
        end_time: Optional[datetime] = None,
        db: Session = None
    ) -> None:
        """
        Generate a daily summary video for the specified date.
        
        Args:
            target_date: Date to generate summary for (YYYY-MM-DD)
            end_time: Optional end time (defaults to end of target_date)
            db: Database session
            
        Returns:
            DailySummary object if successful, None otherwise
        """
        if db is None:
            from app.database import SessionLocal
            db = SessionLocal()
            should_close = True
        else:
            should_close = False
        
        try:
            job.status = DailySummaryJobStatus.PROCESSING
            job.started_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            db.refresh(job)

            # Check if summary already exists
            existing_summary = db.query(DailySummary).filter(
                DailySummary.date == target_date.strftime("%Y-%m-%d")
            ).first()

            if existing_summary:
                if not job.allow_duplicate:
                    logger.info(f"Daily summary already exists for {target_date} and job does not allow duplicate. Linking job to existing summary.")
                    job.status = DailySummaryJobStatus.COMPLETED
                    job.summary_id = existing_summary.id
                    job.completed_at = datetime.now(timezone.utc)
                    db.add(job)
                    db.commit()
                    db.refresh(job)
                    return
                else:
                    logger.info(f"Daily summary already exists for {target_date} but job allows duplicate. Proceeding with regeneration.")
            
            # Calculate time range
            # Calculate time range using configured timezone
            from app.models import MediaType
            from app.timezone_utils import get_timezone_obj
            
            # Get configured timezone
            tz = get_timezone_obj(db=db)
            
            # Create timezone-aware start/end times for the local day
            local_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz)
            
            if end_time:
                # If end_time is provided, ensure it's timezone aware
                if end_time.tzinfo is None:
                    # Assume input end_time is in local time if naive
                    local_end = end_time.replace(tzinfo=tz)
                else:
                    local_end = end_time.astimezone(tz)
            else:
                local_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=tz)
            
            # Convert to UTC for database query
            # SQLite/SQLAlchemy usually stores naive UTC datetimes
            utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
            utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
            
            logger.info(f"Querying memories for {target_date} ({tz}) -> UTC range: {utc_start} to {utc_end}")
            
            # Query memories using the calculated UTC range
            memories = db.query(Media).filter(
                and_(
                    Media.captured_at >= utc_start,
                    Media.captured_at <= utc_end,
                    Media.type == MediaType.IMAGE,
                    Media.ai_caption.isnot(None)  # Only memories with AI captions
                )
            ).order_by(Media.captured_at).all()
            
            if len(memories) < 3:
                logger.warning(f"Not enough memories ({len(memories)}) for {target_date}. Need at least 3 images with AI captions.")
                
                # Log how many total images exist for this date (without AI caption filter)
                total_images = db.query(Media).filter(
                    and_(
                        Media.captured_at >= utc_start,
                        Media.captured_at <= utc_end,
                        Media.type == MediaType.IMAGE
                    )
                ).count()
                logger.info(f"Total images for {target_date}: {total_images} (but only {len(memories)} have AI captions)")
                # Raise an exception so the API can return a proper error message
                raise ValueError(f"Not enough memories for {target_date}. Found {len(memories)} images with AI captions, but need at least 3. Total images for this date: {total_images}.")
            
            # Select random memories (variable count, but ensure 30-45 second duration)
            # Each memory segment is ~4-6 seconds, so we want 5-8 memories
            num_memories = min(max(3, random.randint(5, 8)), len(memories))
            selected_memories = random.sample(memories, num_memories)
            selected_memories.sort(key=lambda m: m.captured_at)  # Sort by timestamp
            
            logger.info(f"Generating daily summary for {target_date} with {len(selected_memories)} memories")
            
            # Generate AI day summary
            day_summary = await self._generate_ai_day_summary(selected_memories)
            
            # Download music track (free, no API key required)
            track_info = await self.music_service.get_random_instrumental_track()
            music_file = await self.music_service.download_track(track_info)
            
            if not music_file:
                logger.warning("No music file available. Video will be generated with silent audio.")
            
            # Create video
            video_path = await self._create_video(
                selected_memories,
                day_summary,
                target_date,
                music_file,
                track_info
            )
            
            if not video_path:
                logger.error("Failed to create video")
                raise Exception("Failed to create video file (FFmpeg error)")
            
            # Get video metadata
            duration, file_size = self._get_video_metadata(video_path)
            
            # Create database record
            expires_at = datetime.now(timezone.utc) + timedelta(days=settings.video_retention_days)
            # Save to database
            
            # Check if summary already exists for this date
            existing_summary = db.query(DailySummary).filter(
                DailySummary.date == target_date.strftime("%Y-%m-%d")
            ).first()
            
            if existing_summary:
                logger.info(f"Updating existing daily summary for {target_date}")
                existing_summary.video_path = str(video_path.relative_to(settings.storage_path))
                existing_summary.memory_ids = json.dumps([m.id for m in selected_memories])
                existing_summary.day_summary = day_summary
                existing_summary.music_track_id = track_info.get('track_id')
                existing_summary.music_track_title = track_info.get('title')
                existing_summary.duration_seconds = duration
                existing_summary.file_size_bytes = file_size
                existing_summary.expires_at = expires_at
                daily_summary = existing_summary
            else:
                logger.info(f"Creating new daily summary for {target_date}")
                daily_summary = DailySummary(
                    date=target_date.strftime("%Y-%m-%d"),
                    video_path=str(video_path.relative_to(settings.storage_path)),
                    memory_ids=json.dumps([m.id for m in selected_memories]),
                    music_track_id=track_info.get('track_id'),
                    music_track_title=track_info.get('title'),
                    day_summary=day_summary,
                    expires_at=expires_at,
                    duration_seconds=duration,
                    file_size_bytes=file_size
                )
                db.add(daily_summary)
            
            db.commit()
            db.refresh(daily_summary)

            job.status = DailySummaryJobStatus.COMPLETED
            job.summary_id = daily_summary.id
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            db.refresh(job)
            
            logger.info(f"Successfully generated daily summary for {target_date}")
            
        except ValueError as e:
            logger.warning(f"Validation error generating daily summary for {target_date}: {e}")
            db.rollback()
            job.status = DailySummaryJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            db.refresh(job)
            raise # Re-raise ValueError so caller knows why it failed
        except Exception as e:
            logger.error(f"Error generating daily summary: {e}", exc_info=True)
            db.rollback()
            job.status = DailySummaryJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            db.refresh(job)
        finally:
            if should_close:
                db.close()
    
    async def _generate_ai_day_summary(self, memories: List[Media]) -> str:
        """Generate AI summary of the day from memory captions."""
        try:
            # Collect all captions
            captions = [m.ai_caption for m in memories if m.ai_caption]
            
            if not captions:
                return "A day full of memories."
            
            # Create prompt
            captions_text = "\n".join([f"- {caption}" for caption in captions[:15]])  # Limit to 15
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates concise, warm summaries of daily memories."
                },
                {
                    "role": "user",
                    "content": (
                        f"Here are some moments from a day:\n\n{captions_text}\n\n"
                        "Create a short, warm, and engaging summary (max 30 words) that captures the vibe of this day. "
                        "The summary will be displayed on a video ending card, so it must be brief and easy to read quickly."
                    )
                }
            ]
            
            summary = await self.ollama_service.chat_completion(messages)
            return summary.strip().replace('"', '')
            
        except Exception as e:
            logger.error(f"Error generating AI day summary: {e}")
            return "A day full of memories."
    
    async def _create_video(
        self,
        memories: List[Media],
        day_summary: str,
        target_date: date,
        music_file: Optional[Path],
        track_info: Dict
    ) -> Optional[Path]:
        """Create the video file using FFmpeg."""
        try:
            # Create title screen
            title_image = self._create_title_screen(target_date)
            
            # Create ending card
            ending_image = self._create_ending_card(day_summary)
            
            # Prepare memory images with text overlays
            memory_segments = []
            for memory in memories:
                segment = await self._prepare_memory_segment(memory)
                if segment:
                    memory_segments.append(segment)
            
            if not memory_segments:
                logger.error("No memory segments prepared")
                return None
            
            # Build FFmpeg command
            # Use unique filename with timestamp to avoid file locking issues on Windows
            timestamp = int(time.time())
            output_file = self.videos_path / f"summary_{target_date.strftime('%Y-%m-%d')}_{timestamp}.mp4"
            
            # Create filter complex for combining all segments
            cmd = self._build_ffmpeg_command(
                title_image,
                memory_segments,
                ending_image,
                music_file,
                output_file
            )
            
            # Execute FFmpeg
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr}")
                return None
            
            # Cleanup temp files
            self._cleanup_temp_files([title_image, ending_image] + memory_segments)
            
            logger.info(f"Video created: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error creating video: {e}", exc_info=True)
            return None
    
    def _create_title_screen(self, target_date: date) -> Path:
        """Create title screen image."""
        width, height = 1920, 1080
        img = Image.new('RGB', (width, height), color='#1a1a2e')
        draw = ImageDraw.Draw(img)
        
        # Format date text
        date_str = target_date.strftime("%A, %B %d, %Y")
        
        # Try to use a nice font, fallback to default
        try:
            # Try to load a system font
            font_large = ImageFont.truetype("arial.ttf", 72)
            font_small = ImageFont.truetype("arial.ttf", 48)
        except:
            try:
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
        
        # Draw text centered
        bbox = draw.textbbox((0, 0), date_str, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2 - 50
        
        draw.text((x, y), date_str, fill='white', font=font_large)
        
        # Add subtitle
        subtitle = "Daily Memories"
        bbox_sub = draw.textbbox((0, 0), subtitle, font=font_small)
        sub_width = bbox_sub[2] - bbox_sub[0]
        x_sub = (width - sub_width) // 2
        y_sub = y + text_height + 30
        
        draw.text((x_sub, y_sub), subtitle, fill='#cccccc', font=font_small)
        
        # Save to temp file
        output_path = self.temp_dir / f"title_{target_date.strftime('%Y-%m-%d')}.png"
        img.save(output_path)
        return output_path
    
    def _create_ending_card(self, summary: str) -> Path:
        """Create ending card with AI summary."""
        width, height = 1920, 1080
        img = Image.new('RGB', (width, height), color='#0f3460')
        draw = ImageDraw.Draw(img)
        
        # Try to use a nice font
        try:
            font_title = ImageFont.truetype("arial.ttf", 64)
            font_text = ImageFont.truetype("arial.ttf", 42)
        except:
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
                font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
            except:
                font_title = ImageFont.load_default()
                font_text = ImageFont.load_default()
        
        # Title
        title = "Today's Summary"
        bbox_title = draw.textbbox((0, 0), title, font=font_title)
        title_width = bbox_title[2] - bbox_title[0]
        x_title = (width - title_width) // 2
        y_title = height // 3
        
        draw.text((x_title, y_title), title, fill='white', font=font_title)
        
        # Summary text (wrap if needed)
        max_width = width - 200
        words = summary.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font_text)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Draw lines
        y_text = y_title + 100
        for line in lines[:5]:  # Limit to 5 lines
            bbox_line = draw.textbbox((0, 0), line, font=font_text)
            line_width = bbox_line[2] - bbox_line[0]
            x_line = (width - line_width) // 2
            draw.text((x_line, y_text), line, fill='#e0e0e0', font=font_text)
            y_text += 60
        
        # Save to temp file
        output_path = self.temp_dir / "ending.png"
        img.save(output_path)
        return output_path
    
    async def _prepare_memory_segment(self, memory: Media) -> Optional[Path]:
        """Prepare a memory image with text overlay."""
        try:
            # Load original image
            image_path = settings.storage_path / memory.media_path
            if not image_path.exists():
                logger.warning(f"Image not found: {image_path}")
                return None
            
            img = Image.open(image_path)
            
            # Resize to 1920x1080 maintaining aspect ratio
            img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            
            # Create new image with black background
            output = Image.new('RGB', (1920, 1080), color='black')
            
            # Center the image
            x = (1920 - img.width) // 2
            y = (1080 - img.height) // 2
            output.paste(img, (x, y))
            
            # Add text overlay at bottom
            draw = ImageDraw.Draw(output)
            
            # Try to use a nice font
            try:
                font = ImageFont.truetype("arial.ttf", 32)
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
                except:
                    font = ImageFont.load_default()
            
            # Get caption text
            caption = memory.ai_caption or "Memory"
            
            # Wrap text
            max_width = 1920 * 0.8
            words = caption.split()
            lines = []
            current_line = []
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            # Draw background box
            line_height = 50
            padding = 20
            box_height = len(lines) * line_height + padding * 2
            box_y = 1080 - box_height - 30
            
            overlay = Image.new('RGBA', (1920, box_height + 30), (0, 0, 0, 180))
            output.paste(overlay, (0, box_y), overlay)
            
            # Draw text
            y_pos = box_y + padding
            for line in lines[:3]:  # Limit to 3 lines
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                x_pos = (1920 - line_width) // 2
                draw.text((x_pos, y_pos), line, fill='white', font=font)
                y_pos += line_height
            
            # Save to temp file
            output_path = self.temp_dir / f"memory_{memory.id}.png"
            output.save(output_path)
            return output_path
            
        except Exception as e:
            logger.error(f"Error preparing memory segment: {e}")
            return None
    
    def _build_ffmpeg_command(
        self,
        title_image: Path,
        memory_segments: List[Path],
        ending_image: Path,
        music_file: Optional[Path],
        output_file: Path
    ) -> List[str]:
        """Build FFmpeg command to create the video with transitions."""
        # Available transitions for xfade
        # We exclude some that might look weird or require specific aspect ratios
        transitions = [
            "fade", "wipeleft", "wiperight", "wipeup", "wipedown", 
            "slideleft", "slideright", "slideup", "slidedown", 
            "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite", 
            "radial", "smoothleft", "smoothright", "smoothup", "smoothdown", 
            "circleopen", "circleclose"
        ]
        
        # Duration settings
        title_duration = 3.0
        memory_duration = 5.0
        ending_duration = 4.0
        transition_duration = 1.0
        
        # All video inputs: Title -> Memories -> Ending
        video_inputs = [title_image] + memory_segments + [ending_image]
        durations = [title_duration] + [memory_duration] * len(memory_segments) + [ending_duration]
        
        # Build command
        cmd = ['ffmpeg', '-y']
        
        # Add inputs
        for inp in video_inputs:
            cmd.extend(['-loop', '1', '-t', '10', '-i', str(inp)]) # Load with extra buffer for transitions
            
        # Add music input
        if music_file and music_file.exists():
            cmd.extend(['-i', str(music_file)])
            has_music = True
            audio_idx = len(video_inputs)
        else:
            has_music = False
        
        # Build complex filter
        filters = []
        
        # 1. Scale and prepare all video inputs
        for i in range(len(video_inputs)):
            # Force scale, set SAR, set FPS, and trim to specific duration + transition buffer
            # We need enough duration for the clip + overlap
            # For the first clip, it's just duration
            # For middle clips, we need overlap on both ends?
            # Actually with xfade, we just stream them.
            # Let's standardize all to 1920x1080 @ 30fps
            filters.append(
                f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]"
            )
            
        # 2. Chain xfades
        # We start with [v0]
        # Then xfade [v0][v1] -> [v01]
        # Then xfade [v01][v2] -> [v012] ...
        
        # Calculate offsets
        # Offset is the cumulative duration of previous clips MINUS the cumulative transition overlaps
        
        current_stream = "[v0]"
        current_offset = durations[0]
        
        for i in range(1, len(video_inputs)):
            next_stream = f"[v{i}]"
            result_stream = f"[v_m{i}]" if i < len(video_inputs) - 1 else "[video_final]"
            
            # Pick a random transition
            trans = random.choice(transitions)
            
            # The offset for xfade is when the transition STARTS.
            # So it should be `current_offset - transition_duration`
            xfade_offset = current_offset - transition_duration
            
            filters.append(
                f"{current_stream}{next_stream}xfade=transition={trans}:duration={transition_duration}:offset={xfade_offset}{result_stream}"
            )
            
            # Update current offset for the NEXT transition
            # The new stream is now (current_offset + next_duration - transition_duration) long
            # minus the transition duration?
            # No.
            # Clip A (5s) + Clip B (5s) with 1s fade.
            # Offset = 5 - 1 = 4s.
            # Result length = 4s (A) + 1s (Overlap) + 4s (B) = 9s.
            # Mathematically: New Duration = Old Duration + New Clip Duration - Transition Duration
            
            current_offset = current_offset + durations[i] - transition_duration
            current_stream = result_stream

        # Total video duration is `current_offset`
        total_duration = current_offset
        
        # 3. Audio handling
        if has_music:
            # Fade out audio at the end
            filters.append(
                f"[{audio_idx}:a]volume=0.25,afade=t=in:st=0:d=1,afade=t=out:st={total_duration-1}:d=1[audio_final]"
            )
            map_a = "[audio_final]"
        else:
            # Silent audio
            filters.append(f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={total_duration}[audio_final]")
            map_a = "[audio_final]"

        cmd.extend(['-filter_complex', ";".join(filters)])
        cmd.extend(['-map', '[video_final]', '-map', map_a])
        
        # Encoding settings
        cmd.extend(['-c:v', 'libx264', '-preset', 'medium', '-crf', '23'])
        cmd.extend(['-pix_fmt', 'yuv420p'])  # Force yuv420p for Android compatibility
        cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
        
        # Trim exact duration to be safe
        cmd.extend(['-t', str(total_duration)])
        
        cmd.append(str(output_file))
        
        return cmd
    
    def _get_video_metadata(self, video_path: Path) -> Tuple[int, int]:
        """Get video duration and file size."""
        try:
            # Get duration using ffprobe
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration = int(float(result.stdout.strip()))
            
            # Get file size
            file_size = video_path.stat().st_size
            
            return duration, file_size
            
        except Exception as e:
            logger.error(f"Error getting video metadata: {e}")
            return 0, 0
    
    def _cleanup_temp_files(self, files: List[Path]):
        """Clean up temporary files."""
        for file in files:
            try:
                if file and file.exists():
                    file.unlink()
            except Exception as e:
                logger.warning(f"Error cleaning up temp file {file}: {e}")

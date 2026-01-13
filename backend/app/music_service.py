"""Free music service - downloads real instrumental music from free sources (no API key required)."""
import logging
import random
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class MusicService:
    """Service for downloading free instrumental background music from public sources."""
    
    CACHE_DIR = Path(settings.storage_path) / "music_cache"
    
    # Free instrumental music tracks from SoundHelix (free, no API key required)
    # SoundHelix provides algorithmically generated instrumental music
    # These are actual MP3 files with real instrumental music
    FREE_MUSIC_TRACKS = [
        {
            'track_id': 'soundhelix_1',
            'title': 'Ambient Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'
        },
        {
            'track_id': 'soundhelix_2',
            'title': 'Calm Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3'
        },
        {
            'track_id': 'soundhelix_3',
            'title': 'Peaceful Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3'
        },
        {
            'track_id': 'soundhelix_4',
            'title': 'Gentle Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3'
        },
        {
            'track_id': 'soundhelix_5',
            'title': 'Soft Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3'
        },
        {
            'track_id': 'soundhelix_6',
            'title': 'Uplifting Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3'
        },
        {
            'track_id': 'soundhelix_7',
            'title': 'Relaxing Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3'
        },
        {
            'track_id': 'soundhelix_8',
            'title': 'Thoughtful Instrumental',
            'artist': 'SoundHelix',
            'download_url': 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3'
        }
    ]
    
    def __init__(self):
        self.cache_dir = self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_random_instrumental_track(self) -> Dict:
        """
        Get a random instrumental track from free music sources.
        Uses GitHub raw URLs from SoundSafari CC0-1.0-Music repository (no API key required).
        
        Returns:
            Dict with track info: {
                'track_id': str,
                'title': str,
                'artist': str,
                'download_url': str,
                'file_url': str
            }
        """
        # Randomly select a track from our free music collection
        track = random.choice(self.FREE_MUSIC_TRACKS)
        logger.info(f"Selected free instrumental music: {track['title']} by {track['artist']}")
        return {
            'track_id': track['track_id'],
            'title': track['title'],
            'artist': track['artist'],
            'download_url': track['download_url'],
            'file_url': track['download_url']
        }
    
    
    
    async def download_track(self, track_info: Dict) -> Optional[Path]:
        """
        Download a track file to local cache.
        
        Args:
            track_info: Track info dict from get_random_instrumental_track()
            
        Returns:
            Path to downloaded file, or None if download failed
        """
        download_url = track_info.get('download_url')
        if not download_url:
            logger.warning("No download URL available")
            return None
        
        try:
            track_id = track_info['track_id']
            cache_file = self.cache_dir / f"{track_id}.mp3"
            
            # Check if already cached
            if cache_file.exists():
                logger.info(f"Using cached music file: {cache_file}")
                return cache_file
            
            # Download the track
            logger.info(f"Downloading instrumental music from: {download_url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'audio/mpeg, audio/*, */*',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(download_url)
                
                if response.status_code == 200:
                    # Verify it's actually audio content
                    content_type = response.headers.get('content-type', '').lower()
                    content_size = len(response.content)
                    
                    # Check for valid MP3 file (starts with ID3 tag or MP3 frame sync)
                    is_audio = (
                        'audio' in content_type or 
                        content_size > 1000 or  # Reasonable file size
                        response.content[:3] == b'ID3' or  # ID3 tag
                        response.content[:2] == b'\xff\xfb' or  # MP3 frame sync
                        response.content[:2] == b'\xff\xf3' or  # MP3 frame sync variant
                        response.content[:2] == b'\xff\xf2'  # MP3 frame sync variant
                    )
                    
                    if is_audio:
                        cache_file.write_bytes(response.content)
                        logger.info(f"Downloaded instrumental music to: {cache_file} ({content_size} bytes)")
                        return cache_file
                    else:
                        logger.warning(f"Downloaded content doesn't appear to be audio (content-type: {content_type}, size: {content_size})")
                        # Try a different track
                        return await self._try_fallback_download()
                else:
                    logger.warning(f"Failed to download track: HTTP {response.status_code}, trying alternative URL patterns")
                    # Try alternative Archive.org URL patterns
                    return await self._try_alternative_urls(track_info)
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout downloading track: {download_url}")
            return await self._try_fallback_download()
        except Exception as e:
            logger.error(f"Error downloading track: {e}")
            return await self._try_fallback_download()
    
    async def _try_alternative_urls(self, track_info: Dict) -> Optional[Path]:
        """Try alternative download URL patterns for Archive.org items."""
        track_id = track_info['track_id']
        cache_file = self.cache_dir / f"{track_id}.mp3"
        
        # Try different Archive.org URL patterns
        archive_id = track_info.get('archive_id') or track_id.replace('archive_', '')
        original_url = track_info.get('download_url', '')
        
        if archive_id:
            # Extract identifier from original URL or use archive_id
            url_patterns = [
                original_url,
                original_url.replace('.mp3', '_64kb.mp3'),
                original_url.replace('.mp3', '_128kb.mp3'),
                f"https://archive.org/download/{archive_id}/{archive_id}.mp3",
                f"https://archive.org/download/{archive_id}/{archive_id}_64kb.mp3",
                f"https://archive.org/download/{archive_id}/{archive_id}_128kb.mp3",
            ]
            
            for url in url_patterns:
                if not url:
                    continue
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'audio/mpeg, audio/*, */*',
                        'Referer': 'https://archive.org/',
                    }
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                        response = await client.get(url)
                        if response.status_code == 200 and len(response.content) > 1000:
                            cache_file.write_bytes(response.content)
                            logger.info(f"Downloaded track from alternative URL: {cache_file}")
                            return cache_file
                except Exception:
                    continue
        
        # If all alternatives fail, try a different fallback track
        return await self._try_fallback_download()
    
    async def _try_fallback_download(self) -> Optional[Path]:
        """Try downloading a different track if the first one failed."""
        # Try a few different tracks
        fallback_tracks = random.sample(self.FREE_MUSIC_TRACKS, min(3, len(self.FREE_MUSIC_TRACKS)))
        
        for track in fallback_tracks:
            try:
                cache_file = self.cache_dir / f"{track['track_id']}.mp3"
                
                if cache_file.exists():
                    logger.info(f"Using cached fallback track: {cache_file}")
                    return cache_file
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'audio/mpeg, audio/*, */*',
                }
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
                    response = await client.get(track['download_url'])
                    if response.status_code == 200 and len(response.content) > 1000:
                        cache_file.write_bytes(response.content)
                        logger.info(f"Downloaded fallback instrumental track: {cache_file}")
                        return cache_file
            except Exception as e:
                logger.warning(f"Fallback track download failed: {e}")
                continue
        
        logger.error("All instrumental music download attempts failed")
        return None
    
    
    def cleanup_old_cache(self, days: int = 7):
        """Remove cached music files older than specified days."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            removed = 0
            
            for cache_file in self.cache_dir.glob("*.mp3"):
                if cache_file.stat().st_mtime < cutoff.timestamp():
                    cache_file.unlink()
                    removed += 1
            
            if removed > 0:
                logger.info(f"Cleaned up {removed} old music cache files")
                
        except Exception as e:
            logger.error(f"Error cleaning up music cache: {e}")

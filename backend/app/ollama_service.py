"""Ollama integration for AI image analysis with moondream."""
import base64
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.models import Media
from app.config import settings

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for AI image analysis using remote Ollama with moondream."""

    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_vision_model
        self.chat_model = settings.ollama_chat_model
        self.timeout = settings.ollama_timeout
        self.chat_timeout = settings.ollama_chat_timeout

    async def analyze_image(
        self,
        image_path: Path,
        prompt: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Analyze an image using Ollama's moondream model.
        """
        if prompt is None:
            # Moondream 1B compatible prompt requesting structured life-capture analysis
            # Request structured format with life-capture focus: people, activities, moments, context
            prompt = (
                "Analyze this photo. Provide:\n"
                "CAPTION: Describe the scene, moment, or activity\n"
                "TAGS: List 5-10 keywords (people, objects, activities, locations, emotions)\n"
                "DETAILS: Note mood, relationships, what's happening, memorable elements"
            )

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Sending analysis request to Ollama: {url} (model: {self.model})")
                response = await client.post(url, json=payload)
                
                if response.status_code != 200:
                    logger.error(f"Ollama returned error {response.status_code}: {response.text}")
                    # Try fallback if model was the issue
                    if "not found" in response.text.lower() and ":" in self.model:
                        base_model = self.model.split(":")[0]
                        logger.info(f"Retrying with base model name: {base_model}")
                        payload["model"] = base_model
                        response = await client.post(url, json=payload)

                response.raise_for_status()
                result = response.json()
                
                # Debug: log the full response structure to diagnose issues
                logger.debug(f"Ollama response keys: {list(result.keys())}")
                logger.debug(f"Ollama response structure: {json.dumps(result, indent=2)[:500]}")
                
                # Check for error in response
                if "error" in result:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Ollama returned error in response: {error_msg}")
                    raise Exception(f"Ollama error: {error_msg}")
                
                raw_response = result.get("response", "").strip()

                if not raw_response:
                    # Log the full result to help diagnose
                    logger.error(f"Ollama returned empty response. Full result: {json.dumps(result)[:500]}")
                    logger.warning(f"Ollama returned empty response for {image_path}")
                    raise Exception("Empty response from Ollama")

                parsed = self._parse_response(raw_response)
                return {
                    "caption": parsed["caption"],
                    "tags": parsed["tags"],
                    "confidence": parsed["confidence"],
                    "raw_response": raw_response
                }

        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in analyze_image: {e}")
            raise

    def _parse_response(self, response: str) -> Dict[str, any]:
        """Parse response from moondream, handling both structured and free-form."""
        lines = response.strip().split("\n")
        caption = ""
        tags = []
        details = ""

        # Check if it follows the CAPTION/TAGS format
        has_labels = any(line.upper().startswith(("CAPTION:", "TAGS:")) for line in lines)

        if has_labels:
            for line in lines:
                line = line.strip()
                if line.upper().startswith("CAPTION:"):
                    caption = line[8:].strip()
                elif line.upper().startswith("TAGS:"):
                    tags_str = line[5:].strip()
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                elif line.upper().startswith("DETAILS:"):
                    details = line[8:].strip()
        
        # If no caption was found (either no labels or label was empty)
        if not caption:
            # Use the first non-empty line or the whole thing
            non_empty_lines = [l.strip() for l in lines if l.strip()]
            if non_empty_lines:
                caption = non_empty_lines[0]
            else:
                caption = response.strip()

        # If we still have no tags, try to extract some from the caption
        if not tags:
            # Very simple tag extraction: words longer than 4 chars, excluding some common ones
            words = caption.replace(".", "").replace(",", "").split()
            potential_tags = [w.lower() for w in words if len(w) > 4]
            # Limit to 5 tags
            tags = list(dict.fromkeys(potential_tags))[:5]

        confidence = 0.8 if len(caption) > 10 else 0.5
        return {"caption": caption, "tags": tags, "details": details, "confidence": confidence}

    async def analyze_media(self, db: Session, media: Media) -> bool:
        """Analyze a media item and update database record."""
        if media.type.value != "image":
            return False

        if not media.media_path:
            return False

        full_path = settings.storage_path / media.media_path
        if not full_path.exists():
            logger.error(f"Media file not found: {full_path}")
            return False

        try:
            result = await self.analyze_image(full_path)
            media.ai_caption = result["caption"]
            media.ai_tags_json = json.dumps(result["tags"])
            media.ai_confidence = result["confidence"]
            media.ai_analyzed_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"Successfully analyzed media {media.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to analyze media {media.id}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Ollama service is reachable and model is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                logger.info(f"Checking Ollama health at {self.base_url}")
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()

                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                # Flexible matching: moondream matches moondream:latest
                match = any(self.model in name or name in self.model for name in model_names)
                
                if not match:
                    logger.warning(f"Model '{self.model}' not found. Available: {model_names}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def list_available_models(self) -> List[str]:
        """List available models on the Ollama server."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                return [m.get("name", "") for m in models]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []

    async def unload_model(self, model_name: str) -> bool:
        """
        Unload a model from memory to free up VRAM.
        
        Args:
            model_name: Name of the model to unload
            
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/api/generate"
        # To unload, we send a request with keep_alive=0 and empty prompt
        payload = {
            "model": model_name,
            "keep_alive": 0
        }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                logger.info(f"Unloading model {model_name}...")
                await client.post(url, json=payload)
                return True
        except Exception as e:
            logger.warning(f"Failed to unload model {model_name}: {e}")
            return False

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None
    ) -> str:
        """
        Generate chat completion using Ollama's chat API.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
                     e.g., [{"role": "user", "content": "Hello"}]
            model: Optional model name (defaults to ollama_chat_model)
        
        Returns:
            Generated response text
        
        Raises:
            ValueError: If the model is not found or unavailable
            httpx.HTTPError: For HTTP errors
        """
        if model is None:
            model = self.chat_model

        url = f"{self.base_url}/api/chat"
        models_to_try = [model]
        if model != "llama3.2:latest":
            models_to_try.append("llama3.2:latest")
            
        last_exception = None

        for current_model in models_to_try:
            try:
                payload = {
                    "model": current_model,
                    "messages": messages,
                    "stream": False
                }
                
                async with httpx.AsyncClient(timeout=self.chat_timeout) as client:
                    logger.info(f"Sending chat request to Ollama: {url} (model: {current_model})")
                    response = await client.post(url, json=payload)
                    
                    # Handle OOM / Server Error
                    if response.status_code == 500:
                        error_text = response.text.lower()
                        if "out of memory" in error_text or "cuda" in error_text:
                            logger.warning(f"Ollama OOM with {current_model}. Unloading models...")
                            await self.unload_model(self.model)
                            if current_model != self.model:
                                await self.unload_model(current_model)
                            
                            # Retry THIS model once after unload? 
                            # Or just let the loop continue to fallback?
                            # Let's retry THIS model once.
                            logger.info(f"Retrying {current_model} after cleanup...")
                            response = await client.post(url, json=payload)
                
                # Check status again after potential retry
                if response.status_code != 200:
                    logger.warning(f"Model {current_model} failed with {response.status_code}: {response.text}")
                    # If this was the last model, raise the error
                    if current_model == models_to_try[-1]:
                        response.raise_for_status()
                    else:
                        logger.info(f"Falling back to next model...")
                        continue

                result = response.json()
                message = result.get("message", {})
                content = message.get("content", "").strip()

                if not content:
                    logger.warning(f"Ollama chat returned empty response")
                    raise Exception("Empty response from Ollama chat")

                return content

            except Exception as e:
                logger.error(f"Error with model {current_model}: {e}")
                last_exception = e
                # If valid fallback exists, continue. Else raise.
                if current_model == models_to_try[-1]:
                    raise last_exception
                logger.info(f"Falling back due to exception...")
                continue
                
        if last_exception:
            raise last_exception
        raise Exception("Chat completion failed for unknown reasons")

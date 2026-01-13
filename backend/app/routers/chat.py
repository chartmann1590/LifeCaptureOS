"""AI chat endpoints for querying photos."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.chat_service import ChatService
from app.ollama_service import OllamaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

# In-memory conversation storage
# Format: {conversation_id: List[Dict[str, str]]}
# Each message: {"role": "user"|"assistant", "content": "..."}
conversations: Dict[str, List[Dict[str, str]]] = {}


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    ok: bool = True
    answer: str
    conversation_id: str
    media_references: Optional[List[int]] = None


def get_or_create_conversation(conversation_id: Optional[str]) -> str:
    """Get existing conversation ID or create new one."""
    if conversation_id and conversation_id in conversations:
        return conversation_id
    
    # Create new conversation
    new_id = str(uuid.uuid4())
    conversations[new_id] = []
    return new_id


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Chat endpoint for querying photos with AI.
    
    The AI will search through photo AI summaries and timestamps to answer questions.
    """
    try:
        # Get or create conversation
        conversation_id = get_or_create_conversation(request.conversation_id)
        conversation_history = conversations[conversation_id]

        # Add user message to history
        user_message = {"role": "user", "content": request.message}
        conversation_history.append(user_message)

        # Build media context from query
        chat_service = ChatService(db)
        media_context, media_ids = chat_service.build_media_context(request.message)

        # Build system prompt with media context
        system_prompt = (
            "You are a helpful assistant that answers questions about photos based on their AI-generated summaries.\n\n"
            f"Here are photos from the user's collection:\n{media_context}\n\n"
            "Answer the question based on the photo summaries above. Be concise and specific. "
            "If no relevant photos are found, say so."
        )

        # Build messages for Ollama
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add conversation history (last 10 messages to avoid token limits)
        recent_history = conversation_history[-10:]
        messages.extend(recent_history)

        # Get AI response
        ollama = OllamaService()
        try:
            ai_response = await ollama.chat_completion(messages)
        except ValueError as e:
            # Model not found error - return helpful message to user
            error_msg = str(e)
            logger.error(f"Chat model error: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_msg
            )

        # Add assistant response to history
        assistant_message = {"role": "assistant", "content": ai_response}
        conversation_history.append(assistant_message)

        # Keep conversation history manageable (max 50 messages)
        if len(conversation_history) > 50:
            # Keep system context and last 40 messages
            conversations[conversation_id] = conversation_history[-40:]

        return ChatResponse(
            ok=True,
            answer=ai_response,
            conversation_id=conversation_id,
            media_references=media_ids if media_ids else None
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like model not found)
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat error: {str(e)}"
        )


@router.delete("/chat/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """Clear a conversation history."""
    if conversation_id in conversations:
        del conversations[conversation_id]
        return JSONResponse({"ok": True, "message": "Conversation cleared"})
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

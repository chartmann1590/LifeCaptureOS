# LifeCaptureOS AI Intelligence Guide

LifeCaptureOS transforms raw images into meaningful narratives using local AI and automated video generation. This guide explores the "Memories", "Daily Video Recaps", and "AI Chat" features.

## 1. Core AI Architecture

The system uses **Ollama** as its primary AI engine, running locally (or on a remote server you control).

- **Vision Model**: `moondream` (lightweight vision-language model) - Used for image captioning.
- **Language Model**: `llama3` (or similar) - Used for day summaries and responding to chat queries.

## 2. AI Memories (Image Analysis)

Every image uploaded from the ESP32-CAM is automatically queued for analysis.

- **Captioning**: The `moondream` model analyzes the image and generates a natural language description (e.g., "A photo of a Golden Retriever playing in the park").
- **Tags**: Key entities and themes are extracted and stored as searchable tags.
- **Benefits**: This turns a folder of thousands of generic JPEG files into a searchable, structured database of your life.

## 3. Daily Video Recaps

LifeCaptureOS automatically generates a cinematic video summary of your day.

### How it Works
1.  **Selection**: The system picks 5-8 significant "Memories" from the previous day.
2.  **AI Summary**: It sends all image captions to the LLM to write a warm, cohesive summary of the day's events.
3.  **Music**: It downloads a high-quality instrumental track from a curated free music library.
4.  **Composition**: Using **FFmpeg**, it assembles a video with:
    - Cinematic transitions (fade, wipe, slide, etc.).
    - Text overlays featuring the AI-generated captions.
    - A title card with the date.
    - An ending card with the AI-written day summary.

### Scheduling
By default, the `DailySummaryJob` runs automatically at **05:00 AM** (configurable in `.env`).

### Manual Trigger
You can force a video generation for any date via the Web UI or API:
```bash
# Example API call to generate summary for 2024-01-10
curl -X POST http://localhost:8000/ai/daily-summaries/generate -d '{"date": "2024-01-10"}'
```

## 4. AI Chat

The "Memories" tab in the Web UI featuring a natural language search interface.

- **Semantic Querying**: Instead of searching by date, you can ask:
    - "What did I do last Friday?"
    - "When was the last time I saw the dog?"
    - "Show me photos from my trip last week."
- **Context Filtering**: The `chat_service.py` parses time-based intents (e.g., "this morning", "yesterday") and retrieves relevant analyzed media to construct a helpful response.

## 5. Prerequisites for AI Features

To enable these features, ensure your backend host has:

1.  **Ollama Running**:
    - Reachable at the address set in `OLLAMA_BASE_URL`.
    - `ollama pull moondream`
    - `ollama pull llama3`
2.  **FFmpeg Installed**:
    - Required for video assembly and transitions.
    - `sudo apt install ffmpeg` (Linux) or `brew install ffmpeg` (macOS).

## Check the Status
Visit the `/health` endpoint to verify connectivity:
`http://<YOUR_IP>:8000/health`
- `ollama`: Should be **healthy**.
- `database`: Should be **healthy**.

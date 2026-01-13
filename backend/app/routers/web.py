"""Web UI router for serving React SPA."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path

router = APIRouter()

# Path to React app static files
STATIC_DIR = Path(__file__).parent.parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@router.get("/{path:path}")
async def serve_spa(request: Request, path: str):
    """Serve React SPA - all non-API routes should serve index.html."""
    # FastAPI should match more specific API routes first, so if we reach here,
    # it means no API route matched. Just serve the SPA.
    
    # Check if requesting a static asset (has file extension)
    if "." in path and not path.endswith(".html"):
        # Try to serve static file
        static_file = STATIC_DIR / path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        # If not found, let it fall through to serve index.html for SPA routing
    
    # Serve index.html for all routes (SPA routing)
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML), media_type="text/html")
    else:
        # Fallback if React app hasn't been built yet
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>LifeCaptureOS Backend</title>
            <style>
                body { font-family: sans-serif; padding: 2rem; text-align: center; }
                .message { max-width: 600px; margin: 0 auto; padding: 2rem; background: #f5f5f5; border-radius: 8px; }
                code { background: #e5e5e5; padding: 2px 6px; border-radius: 3px; }
            </style>
        </head>
        <body>
            <div class="message">
                <h1>LifeCaptureOS Backend</h1>
                <p>Web UI is not built yet. Please run:</p>
                <p><code>cd backend/webui && npm install && npm run build</code></p>
                <p><a href="/docs">API Documentation</a></p>
            </div>
        </body>
        </html>
        """)

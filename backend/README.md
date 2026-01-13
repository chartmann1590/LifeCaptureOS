# LifeCaptureOS Backend

FastAPI backend server for receiving uploads from ESP32-CAM devices and running AI analysis via remote Ollama.

## Features

- **Resumable uploads**: Chunked uploads with resume capability
- **AI analysis**: Remote Ollama integration with moondream vision model
- **RESTful API**: FastAPI with auto-generated OpenAPI docs
- **SQLite database**: Simple, file-based storage (scalable to PostgreSQL)
- **Device authentication**: Bearer token auth for ESP32 devices

## Setup

### Prerequisites

- Python 3.11 or higher
- Remote Ollama server with moondream model
- FFmpeg (for daily summary video generation)
  - **Windows**: Download from https://ffmpeg.org/download.html and add to PATH
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt-get install ffmpeg` (Debian/Ubuntu) or `sudo yum install ffmpeg` (RHEL/CentOS)

### Installation

1. **Create virtual environment**:

```bash
cd backend
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Configure environment**:

```bash
cp .env.example .env
# Edit .env with your settings
```

Key settings in `.env`:
```env
STORAGE_DIR=./data
OLLAMA_BASE_URL=http://your-ollama-server:11434
OLLAMA_VISION_MODEL=moondream
DEVICE_SHARED_SECRET=change-this-to-a-random-secret
```

4. **Initialize database**:

```bash
python -m app.main init-db
```

5. **Create a device**:

```bash
python -m app.main create-device lifecaptureos-001 "My First Camera"
```

This will output a device token. Save it - you'll need it for ESP32 provisioning.

Example output:
```
Device created successfully!
Device ID: lifecaptureos-001
Device Token: dev_tok_abc123...

Store this token securely. It will be used by the ESP32.
```

### Running the Server

**Development mode** (with auto-reload):

```bash
python -m app.main
```

**Production mode**:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**With workers** (production):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Server will start on `http://localhost:8000`

## API Documentation

Once running, access interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Overview

### Device Endpoints (for ESP32)

All require `Authorization: Bearer <device_token>` header.

- `POST /device/ping` - Health check and status update
- `POST /device/media/initiate` - Start upload session
- `PUT /device/media/{upload_id}/chunk` - Upload chunk
- `GET /device/media/{upload_id}/status` - Query upload progress
- `POST /device/media/{upload_id}/complete` - Finalize upload
- `DELETE /device/media/{upload_id}` - Abort upload

### Media Endpoints (for app/web UI)

- `GET /media/` - List media with filters
- `GET /media/{id}` - Get media metadata
- `GET /media/{id}/thumb` - Download thumbnail
- `GET /media/{id}/file` - Download original file
- `POST /media/{id}/reanalyze` - Re-run AI analysis
- `GET /media/devices/list` - List all devices

### System Endpoints

- `GET /` - API info
- `GET /health` - Health check (database, Ollama, storage)

## Ollama Integration

### Setup Remote Ollama

1. **Install Ollama** on your server (can be same machine or remote):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2. **Pull moondream model**:

```bash
ollama pull moondream
```

3. **Verify model is available**:

```bash
ollama list
# Should show moondream in the list
```

4. **Configure backend** to point to Ollama:

Edit `.env`:
```env
OLLAMA_BASE_URL=http://localhost:11434  # Or remote IP
OLLAMA_VISION_MODEL=moondream
```

### Test AI Analysis

Upload an image, then trigger analysis:

```bash
curl -X POST http://localhost:8000/media/1/reanalyze
```

Response:
```json
{
  "ok": true,
  "message": "Analysis completed",
  "caption": "A person wearing a camera captures a city street scene",
  "tags": ["person", "camera", "street", "urban", "daylight"]
}
```

## Storage Structure

```
data/
├── app.db              # SQLite database
├── media/              # Original files
│   └── <device_id>/
│       └── YYYY/MM/DD/
│           ├── IMG_*.jpg
│           └── VID_*.mp4
├── thumbs/             # Thumbnails
│   └── <device_id>/
│       └── YYYY/MM/DD/
│           └── THM_*.jpg
└── temp/               # Temporary upload files
```

## CLI Utilities

### Initialize Database

```bash
python -m app.main init-db
```

### Create Device

```bash
python -m app.main create-device <device_id> [name]
```

Example:
```bash
python -m app.main create-device lifecaptureos-kitchen "Kitchen Camera"
```

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
black app/
flake8 app/
```

### Database Migrations

For schema changes, use Alembic (optional, for production):

```bash
pip install alembic
alembic init migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Production Deployment

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t lifecaptureos-backend .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data lifecaptureos-backend
```

### Using systemd

Create `/etc/systemd/system/lifecaptureos-backend.service`:

```ini
[Unit]
Description=LifeCaptureOS Backend API
After=network.target

[Service]
Type=simple
User=lifecaptureos
WorkingDirectory=/opt/lifecaptureos-backend
Environment="PATH=/opt/lifecaptureos-backend/venv/bin"
ExecStart=/opt/lifecaptureos-backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable lifecaptureos-backend
sudo systemctl start lifecaptureos-backend
sudo systemctl status lifecaptureos-backend
```

### HTTPS with Nginx

Create `/etc/nginx/sites-available/lifecaptureos`:

```nginx
server {
    listen 80;
    server_name lifecaptureos.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Large uploads
        client_max_body_size 100M;
        proxy_request_buffering off;
    }
}
```

Enable and get SSL cert:

```bash
sudo ln -s /etc/nginx/sites-available/lifecaptureos /etc/nginx/sites-enabled/
sudo certbot --nginx -d lifecaptureos.example.com
sudo systemctl reload nginx
```

## Troubleshooting

### Database locked error

SQLite doesn't handle concurrent writes well. For production with multiple workers, use PostgreSQL:

1. Install PostgreSQL:
```bash
pip install psycopg2-binary
```

2. Update `database.py`:
```python
SQLALCHEMY_DATABASE_URL = "postgresql://user:pass@localhost/lifecaptureos"
```

### Ollama connection errors

1. **Check Ollama is running**:
```bash
curl http://localhost:11434/api/tags
```

2. **Check model is available**:
```bash
ollama list | grep moondream
```

3. **Check firewall** (if remote):
```bash
sudo ufw allow 11434
```

### Upload failures

1. **Check disk space**:
```bash
df -h
```

2. **Check permissions**:
```bash
ls -la data/
chmod -R 755 data/
```

3. **Check logs**:
```bash
# Server logs show detailed error messages
```

## Performance Tuning

### For many devices (100+)

1. **Use PostgreSQL** instead of SQLite
2. **Run multiple workers**:
```bash
uvicorn app.main:app --workers 4
```

3. **Use Redis for task queue**:
```bash
pip install celery redis
# Offload AI analysis to Celery workers
```

4. **Add caching**:
```bash
pip install fastapi-cache2
# Cache media list responses
```

## Security Notes

- **Change `DEVICE_SHARED_SECRET`** in production
- **Use HTTPS** (not HTTP) in production
- **Restrict CORS origins** in `main.py`
- **Use strong device tokens** (32+ bytes)
- **Regularly backup database**: `cp data/app.db data/app.db.backup`

## License

MIT

# LifeCaptureOS Web UI

React-based web dashboard for the LifeCaptureOS backend.

## Development

### Prerequisites

- Node.js 18+ and npm

### Setup

```bash
cd backend/webui
npm install
```

### Development Server

Run the Vite dev server (with proxy to FastAPI backend):

```bash
npm run dev
```

The UI will be available at http://localhost:3000 and will proxy API requests to the FastAPI backend at http://localhost:8000.

### Building for Production

Build the React app for production:

```bash
npm run build
```

This will output the built files to `backend/app/static/`, which will be served by FastAPI.

After building, restart the FastAPI server to serve the new build.

## Features

- **Dashboard**: Overview of all devices with connection status and statistics
- **Device Details**: Comprehensive device information including storage, usage stats, and recent media
- **Gallery**: Grid view of all synced media with filtering by device and image viewer

## Tech Stack

- React 18
- React Router 6
- Vite (build tool)
- Tailwind CSS (styling)

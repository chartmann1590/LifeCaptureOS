# LifeCaptureOS Web UI Guide

The LifeCaptureOS Web UI is a modern React-based single-page application (SPA) that provides a dashboard for managing your devices and browsing your captured media.

## 1. Prerequisites

- **Node.js**: Version 18 or newer.
- **npm**: Usually comes with Node.js.

## 2. Setup and Development

The Web UI source code is located in the `backend/webui` directory.

### 2.1 Installation
Navigate to the Web UI directory and install dependencies:

```bash
cd backend/webui
npm install
```

### 2.2 Development Server
To work on the UI with hot-reloading:

```bash
npm run dev
```

The development server typically runs on `http://localhost:5173` (or `3000`). It is configured to automatically proxy API requests to the FastAPI backend running on port `8000`.

## 3. Building for Production

For the backend to serve the Web UI directly, you must build the React application and place it in the application's static directory.

### 3.1 Build Command
```bash
npm run build
```

### 3.2 Deployment Flow
1. Running `npm run build` generates a `dist` folder inside `backend/webui`.
2. The project's `vite.config.js` is pre-configured to output these build files into `backend/app/static`.
3. The FastAPI server (in `backend/app/routers/web.py`) serves `index.html` for all non-API requests.

> [!TIP]
> Always rebuild the Web UI after making changes if you intend to serve them through the main backend URL (`http://<YOUR_IP>:8000`).

## 4. Key Features

- **Dashboard**: Real-time overview of connected devices, capture status, and storage usage.
- **Media Gallery**: A responsive grid view of all images with thumbnails. Supports full-res viewing and metadata inspection.
- **Device Management**: View specific logs and statistics for each registered camera.
- **Timeline**: Browse captures chronologically to see your "Story" unfold.

## 5. Technology Stack

- **Framework**: React 18
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **Routing**: React Router 6
- **API Communication**: Standard `fetch` calls to the FastAPI endpoints.

## Troubleshooting

- **"Web UI is not built yet" message**: If you see this when visiting the backend root, it means the `backend/app/static/index.html` file is missing. Run `npm run build` in the `backend/webui` folder.
- **CSS not loading**: Ensure you have run `npm install` and that Tailwind is correctly processing files during the build.
- **Proxy errors during dev**: Verify your backend is running at `http://localhost:8000` before starting the dev server.

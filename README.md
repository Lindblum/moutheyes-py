# Moutheyes

Replace a face's eyes with its own (animated) mouth. Upload a GIF or video, or a photo
(which gets a short reaction animation first), and get a GIF back.

```
backend/moutheyes/   Python: FastAPI app + the image pipeline
  pipeline.py        face tracking, still -> reaction animation, moutheyes compositing
  jobs.py            in-memory job queue (one job at a time)
  storage.py         naming/lookup of files in inputs/ and outputs/
  api.py             HTTP API, also serves media and the built frontend
  cli.py             batch mode over inputs/ (the original script's behaviour)
frontend/            React + TypeScript (Vite)
models/              MediaPipe face landmarker
inputs/, outputs/    uploads and finished GIFs (git-ignored)
```

Requires Python 3.11+, Node 20+, and `ffmpeg` on PATH.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install
```

## Develop

Two terminals:

```powershell
cd backend; ..\.venv\Scripts\python -m uvicorn moutheyes.api:app --reload --port 8000
cd frontend; npm run dev        # http://localhost:5180, proxies /api and /media to :8000
```

## Run as one server

```powershell
cd frontend; npm run build
cd ..\backend; ..\.venv\Scripts\python -m uvicorn moutheyes.api:app --port 8000   # http://localhost:8000
```

## Batch mode

```powershell
cd backend; ..\.venv\Scripts\python -m moutheyes.cli [--force] [--seed N]
```

Set `MOUTHEYES_DATA` to keep `inputs/` and `outputs/` somewhere other than the repo root.

## API

| Method | Path | |
| --- | --- | --- |
| POST | `/api/jobs` | multipart: `file`, `mouth_scale` (0.8–2.5), `reaction` (`random`, `gasp`, `scream`, `chatter`, `double-take`), `seed` |
| GET | `/api/jobs/{id}` | status, stage, progress, result |
| GET | `/api/gallery` | finished GIFs, newest first |
| DELETE | `/api/gallery/{name}` | delete a finished GIF |

# Build the frontend
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python runtime; MediaPipe needs GLES/EGL, the pipeline needs ffmpeg
FROM python:3.11-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgles2 libegl1 libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY models/ models/
COPY --from=frontend /app/frontend/dist frontend/dist

WORKDIR /app/backend
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn moutheyes.api:app --host 0.0.0.0 --port $PORT"]

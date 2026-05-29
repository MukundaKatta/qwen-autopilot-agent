# Backend image for qwen-autopilot-agent, for Alibaba Cloud Function Compute /
# Serverless App Engine (SAE) / ECS / ACK. The core library is stdlib-only; this
# image adds the FastAPI server (server.py) and its deps.
FROM python:3.12-slim

WORKDIR /app

# Install server deps first so the layer caches across code changes.
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Application code only (tests/docs/examples are excluded via .dockerignore).
COPY qwen_autopilot/ ./qwen_autopilot/
COPY server.py .

# DASHSCOPE_API_KEY is provided at runtime as a secret/env var, never baked in.
# Alibaba FC/SAE route traffic to $PORT.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]

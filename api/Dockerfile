# API Dockerfile - FastAPI backend with Google Cloud ADK
# Creates everything from scratch inside the container to avoid Windows file corruption

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy ONLY requirements.txt (context is ./api, so this is api/requirements.txt)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create app directory structure from scratch
RUN mkdir -p app/agents app/routers

# Create __init__.py files
RUN touch app/__init__.py app/agents/__init__.py app/routers/__init__.py

# Create main.py from scratch inside the container
RUN cat > app/main.py << 'ENDPYTHON'
from fastapi import FastAPI

app = FastAPI(title="Screenplay Clearance API")


@app.get("/health")
async def health():
    return {"ok": True}
ENDPYTHON

# Create a simple config.py
RUN cat > app/config.py << 'ENDPYTHON'
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://clearance:clearance@db:5432/clearance")
    upload_dir: str = os.getenv("UPLOAD_DIR", "/data/uploads")
    google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-2.5-flash")
    assessment_model: str = os.getenv("ASSESSMENT_MODEL", "gemini-2.5-pro")

settings = Settings()
ENDPYTHON

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Start uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

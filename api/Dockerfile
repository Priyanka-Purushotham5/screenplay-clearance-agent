# API image, FastAPI + the ADK agent.
#
# The build context is the REPO ROOT, not ./api. The application imports
# itself as `api.app.*` (see api/app/db.py), so the repo root has to be the
# working directory inside the container too. docker-compose.yml sets:
#
#     build:
#       context: .
#       dockerfile: api/Dockerfile

FROM python:3.11-slim

# postgresql-client gives us psql inside the container for debugging.
# build-essential covers the few wheels that ship without binaries.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Dependencies first, so editing code does not invalidate the pip layer.
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# The real application code. api/__init__.py makes `api` a package, which
# is what lets `from api.app.config import settings` resolve.
COPY api/ api/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8080'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health', timeout=4).status == 200 else 1)"

EXPOSE 8080

# Shell form on purpose, so $PORT expands at runtime. Managed hosts assign a
# port through that variable and route to it; a container listening on a
# hard-coded 8080 is simply never reached, and the platform reports it as a
# failed health check rather than as the misconfiguration it is.
# Compose overrides this entirely with --reload for development.
CMD ["sh", "-c", "uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
"""FastAPI application entry point.

Run from the repo root, so that the `api.app.*` imports resolve:

    uvicorn api.app.main:app --host 0.0.0.0 --port 8080

The OpenAPI schema this serves is not decorative, `npm run gen:types` in
web/ generates the frontend's TypeScript client straight from
http://localhost:8080/openapi.json.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app import errors
from api.app.config import settings
from api.app.logging_config import configure_logging

# Before the routers are imported, so that anything logged during import — and
# everything the background runs log afterwards — reaches stdout. Without this
# the root logger has no handler and every logger.info in the application is
# silently discarded; see api/app/logging_config.py.
configure_logging()

from api.app.routers import runs, scripts  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    logging.getLogger(__name__).info(
        "clearance API up (models: extraction=%s assessment=%s)",
        settings.extraction_model, settings.assessment_model,
    )
    yield


app = FastAPI(
    title="Screenplay Clearance API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

errors.register(app)
app.include_router(scripts.router)
app.include_router(runs.router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"ok": True}
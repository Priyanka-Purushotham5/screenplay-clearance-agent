"""FastAPI application entry point.

Run from the repo root, so that the `api.app.*` imports resolve:

    uvicorn api.app.main:app --host 0.0.0.0 --port 8080

The OpenAPI schema this serves is not decorative, `npm run gen:types` in
web/ generates the frontend's TypeScript client straight from
http://localhost:8080/openapi.json.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app import errors
from api.app.config import settings
from api.app.routers import scripts


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
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


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"ok": True}
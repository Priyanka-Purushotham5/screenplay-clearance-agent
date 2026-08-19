"""POST /api/scripts — upload, validate, dedup, store. 

Parsing is not here yet: `scene_count` stays 0 until B5 groups scenes, and
the title is derived from the filename until B4 can read the title page.
The page count *is* real,  it doubles as the "this is a readable PDF" gate.

Path parameter is named `id`, not `script_id`, because the frontend's
generated client calls `apiClient.GET("/api/scripts/{id}")`. Renaming it
would break `npm run gen:types`.
"""

from __future__ import annotations

import uuid
from contextlib import suppress

import anyio.to_thread
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import settings
from api.app.db import get_session
from api.app.errors import ApiError
from api.app.models import Script
from api.app.parser.pdf import UnparseablePDF, page_count
from api.app.schemas import ERROR_RESPONSES, ApiErrorOut, ScriptOut
from api.app.uploads import (
    EmptyUpload,
    NotAPDF,
    UploadTooLarge,
    commit,
    derive_title,
    stage_upload,
    storage_key,
)

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


def _out(script: Script, duplicate_of: uuid.UUID | None = None) -> ScriptOut:
    return ScriptOut(
        script_id=script.id,
        title=script.title,
        source_format=script.source_format,
        page_count=script.page_count,
        scene_count=script.scene_count,
        parse_warnings=script.parse_warnings or [],
        duplicate_of=duplicate_of,
    )


async def _by_sha(session: AsyncSession, sha256: str) -> Script | None:
    result = await session.execute(select(Script).where(Script.sha256 == sha256))
    return result.scalar_one_or_none()


def _too_large() -> ApiError:
    mb = settings.max_upload_bytes // (1024 * 1024)
    return ApiError(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "FILE_TOO_LARGE",
        f"Upload exceeds the {mb} MB limit.",
    )


@router.post(
    "",
    response_model=ScriptOut,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Upload a screenplay PDF",
)
async def create_script(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ScriptOut:
    # 0. Cheap rejection on the declared length 
    # Starlette has already buffered the body by the time this runs, so
    # this is the earliest an oversized upload can be refused. It is only
    # an optimisation, Content-Length is client-supplied and can lie, so
    # the streaming check below is the one that actually decides.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        # Multipart framing adds a few hundred bytes; 1 MB of slack stops a
        # legitimate 25 MB file tripping on the envelope.
        if int(declared) > settings.max_upload_bytes + 1024 * 1024:
            raise _too_large()

    # 1. Stream to disk: size cap, magic bytes, SHA-256, one pass
    try:
        staged = await stage_upload(
            file,
            upload_dir=settings.upload_dir,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadTooLarge:
        raise _too_large() from None
    except NotAPDF:
        raise ApiError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_TYPE",
            "Only PDF uploads are supported.",
        ) from None
    except EmptyUpload:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "EMPTY_FILE",
            "The uploaded file is empty.",
        ) from None

    try:
        # 2. Dedup on content, not filename
        # 201 rather than 200, even though nothing was created: the upload
        # screen in web/app/page.tsx treats any non-201 as a failure, and
        # technical-spec.md §7 documents only 201. `duplicate_of` is how
        # the caller tells the two apart.
        existing = await _by_sha(session, staged.sha256)
        if existing is not None:
            return _out(existing, duplicate_of=existing.id)

        # 3. Page count, off-thread
        # pdfplumber is slow and blocking, and this worker also has to
        # serve the SSE stream in Block C.
        try:
            pages = await anyio.to_thread.run_sync(page_count, staged.path)
        except UnparseablePDF as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNPARSEABLE_PDF",
                "The file starts with %PDF but could not be opened.",
            ) from exc

        #  4. Move into permanent storage
        script_id = uuid.uuid4()
        key = storage_key(script_id)
        stored = commit(staged.path, settings.upload_dir, key)

        #   5. Insert
        script = Script(
            id=script_id,
            title=derive_title(file.filename),
            filename=file.filename or "upload.pdf",
            storage_path=key,
            sha256=staged.sha256,
            source_format="pdf",
            page_count=pages,
            scene_count=0,  # B5 fills this in
            parse_warnings=[],
        )
        session.add(script)
        try:
            await session.commit()
        except IntegrityError:
            # Two identical files uploaded concurrently: the sha256 UNIQUE
            # constraint picks the winner. The loser hands back the winner
            # and removes its own copy, or we accumulate orphan directories
            # that no row points at.
            await session.rollback()
            stored.unlink(missing_ok=True)
            with suppress(OSError):
                stored.parent.rmdir()
            winner = await _by_sha(session, staged.sha256)
            if winner is None:
                raise
            return _out(winner, duplicate_of=winner.id)

        await session.refresh(script)
        return _out(script)

    finally:
        # No-op once the file has been committed; the safety net for every
        # path that raised before that point.
        staged.path.unlink(missing_ok=True)


@router.get(
    "/{id}",
    response_model=ScriptOut,
    responses={404: {"model": ApiErrorOut, "description": "No such script"}},
    summary="Script metadata",
)
async def get_script(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ScriptOut:
    script = await session.get(Script, id)
    if script is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "SCRIPT_NOT_FOUND",
            "No script with that id.",
        )
    return _out(script)
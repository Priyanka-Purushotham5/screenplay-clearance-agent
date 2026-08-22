"""POST /api/scripts — upload, validate, dedup, parse, store.

The upload is synchronous: the file is parsed into scenes and elements
before the response returns, so a script that cannot be parsed is rejected
while the user still has it in hand. Scenes and script_elements are written
in the same transaction as the scripts row.

The title is still derived from the filename; reading it off the title page
is not implemented.

Path parameter is named `id`, not `script_id`, because the frontend's
generated client calls `apiClient.GET("/api/scripts/{id}")`. Renaming it
would break `npm run gen:types`.
"""

from __future__ import annotations

import uuid
from contextlib import suppress

import anyio.to_thread
from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.app.config import settings
from api.app.db import get_session
from api.app.errors import ApiError
from api.app.models import Scene, Script, ScriptElement
from api.app.parser.pdf import UnparseablePDF, inspect_pdf
from api.app.parser.pipeline import ParsedScript, parse_screenplay
from api.app.schemas import (
    ERROR_RESPONSES,
    ApiErrorOut,
    SceneOut,
    ScenesOut,
    ScriptElementOut,
    ScriptOut,
)
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


def _attach_scenes(script: Script, parsed: ParsedScript) -> None:
    """Hang scenes and their elements off the Script.

    Built as one object graph rather than three sets of inserts: SQLAlchemy
    emits it inside a single transaction, so a failure half way through
    leaves no script row pointing at a partial parse. The spec is explicit
    that scenes and script_elements are written "in one transaction".
    """
    for draft in parsed.scenes:
        scene = Scene(
            script_id=script.id,
            number=draft.number,
            int_ext=draft.int_ext,
            location=draft.location,
            time_of_day=draft.time_of_day,
            heading=draft.heading,
            page_start=draft.page_start,
            page_end=draft.page_end,
        )
        for seq, element in enumerate(draft.elements, start=1):
            scene.elements.append(
                ScriptElement(
                    seq=seq,  # 1-based, matching web/lib/fixtures
                    type=element.type,
                    character=element.character,
                    page=element.page,
                    text=element.text,
                )
            )
        script.scenes.append(scene)


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
    # 0. Cheap rejection on the declared length.
    # Starlette has already buffered the body by the time this runs, so this
    # is the earliest an oversized upload can be refused. It is only an
    # optimisation: Content-Length is client-supplied and can lie, so the
    # streaming check below is the one that actually decides.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        # Multipart framing adds a few hundred bytes; 1 MB of slack stops a
        # legitimate 25 MB file tripping on the envelope.
        if int(declared) > settings.max_upload_bytes + 1024 * 1024:
            raise _too_large()

    # 1. Stream to disk: size cap, magic bytes, SHA-256, one pass.
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
        # 2. Dedup on content, not filename.
        # 201 rather than 200, even though nothing was created: the upload
        # screen in web/app/page.tsx treats any non-201 as a failure, and
        # the spec documents only 201. `duplicate_of` tells the two apart.
        # This sits above the parse, so a re-upload is never re-parsed.
        existing = await _by_sha(session, staged.sha256)
        if existing is not None:
            return _out(existing, duplicate_of=existing.id)

        # 3. Inspect the PDF, off-thread.
        # pdfplumber is slow and blocking, and this worker also has to serve
        # the SSE stream in Block C.
        try:
            report = await anyio.to_thread.run_sync(inspect_pdf, staged.path)
        except UnparseablePDF as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNPARSEABLE_PDF",
                "The file starts with %PDF but could not be opened.",
            ) from exc

        # 3b. Reject scans before anything is stored (B3).
        # A scan is a photograph of a page: visually complete, textually
        # empty. Rejecting it here means the user finds out while the file
        # is still in front of them, and nothing unusable enters storage.
        # Cheap (10 pages) and it gates the expensive parse below.
        if not report.has_text_layer:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "NO_TEXT_LAYER",
                "This PDF has no text layer - it looks like a scan. "
                "Re-export it from the original, or use a text-based PDF.",
                pages_checked=report.pages_checked,
            )

        # 3c. Parse into scenes and elements, off-thread (B2-B5).
        # Synchronous by design: the spec wants a bad file rejected while
        # the user still has it in hand. ~5s for a feature-length script,
        # all of it inside pdfplumber, so it cannot run on the event loop.
        try:
            parsed = await anyio.to_thread.run_sync(parse_screenplay, staged.path)
        except UnparseablePDF as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "UNPARSEABLE_PDF",
                "The file could not be parsed as a screenplay.",
            ) from exc

        # 4. Move into permanent storage.
        script_id = uuid.uuid4()
        key = storage_key(script_id)
        stored = commit(staged.path, settings.upload_dir, key)

        # 5. Insert the script, its scenes and their elements together.
        script = Script(
            id=script_id,
            title=derive_title(file.filename),
            filename=file.filename or "upload.pdf",
            storage_path=key,
            sha256=staged.sha256,
            source_format="pdf",
            page_count=report.page_count,
            scene_count=parsed.scene_count,
            # Advisory, never fatal: a mostly-text script with a few image
            # pages is still worth clearing, the user just needs to know.
            parse_warnings=report.warnings() + parsed.warnings,
        )
        _attach_scenes(script, parsed)
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
    "/{id}/scenes",
    response_model=ScenesOut,
    responses={404: {"model": ApiErrorOut, "description": "No such script"}},
    summary="Parsed scenes, with their elements",
)
async def get_scenes(
    id: uuid.UUID,
    from_: int | None = Query(None, alias="from", description="First scene number"),
    to: int | None = Query(None, description="Last scene number, inclusive"),
    session: AsyncSession = Depends(get_session),
) -> ScenesOut:
    script = await session.get(Script, id)
    if script is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "SCRIPT_NOT_FOUND",
            "No script with that id.",
        )

    # selectinload issues one extra query for all the elements rather than
    # one per scene. Without it a 94-scene script costs 95 round trips.
    query = (
        select(Scene)
        .where(Scene.script_id == id)
        .options(selectinload(Scene.elements))
        .order_by(Scene.number)
    )
    if from_ is not None:
        query = query.where(Scene.number >= from_)
    if to is not None:
        query = query.where(Scene.number <= to)

    scenes = (await session.execute(query)).scalars().all()
    return ScenesOut(
        scenes=[
            SceneOut(
                id=s.id,
                script_id=s.script_id,
                number=s.number,
                int_ext=s.int_ext,
                location=s.location,
                time_of_day=s.time_of_day,
                heading=s.heading,
                page_start=s.page_start,
                page_end=s.page_end,
                elements=sorted(
                    (ScriptElementOut.model_validate(e) for e in s.elements),
                    key=lambda e: e.seq,
                ),
            )
            for s in scenes
        ]
    )


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
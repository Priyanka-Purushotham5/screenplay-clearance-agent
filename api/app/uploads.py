"""Upload streaming: size cap, magic bytes, and hashing in a single pass.

The bytes are never fully buffered by us and never fully written before
they are checked. An oversized upload is abandoned mid-write and the
partial temp file is removed before the request returns.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

PDF_MAGIC = b"%PDF"
CHUNK_SIZE = 1024 * 1024  # 1 MB


class UploadTooLarge(Exception):
    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        super().__init__(f"file exceeds {limit_bytes} bytes")


class NotAPDF(Exception):
    """The leading bytes were not the %PDF magic number."""


class EmptyUpload(Exception):
    """Zero-byte upload."""


class _AsyncReadable(Protocol):
    async def read(self, size: int) -> bytes: ...


@dataclass(frozen=True)
class StagedUpload:
    path: Path
    sha256: str
    size_bytes: int


def temp_dir_for(upload_dir: str | Path) -> Path:
    d = Path(upload_dir) / ".tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def stage_upload(
    source: _AsyncReadable,
    *,
    upload_dir: str | Path,
    max_bytes: int,
) -> StagedUpload:
    digest = hashlib.sha256()
    total = 0
    header = b""
    header_checked = False

    tmp_path = temp_dir_for(upload_dir) / f"upload-{uuid.uuid4().hex}.part"
    fh: BinaryIO = open(tmp_path, "wb")

    try:
        while True:
            chunk = await source.read(CHUNK_SIZE)
            if not chunk:
                break

            total += len(chunk)
            if total > max_bytes:
                raise UploadTooLarge(max_bytes)

            if not header_checked:
                header += chunk[: len(PDF_MAGIC) - len(header)]
                if len(header) >= len(PDF_MAGIC):
                    if header != PDF_MAGIC:
                        raise NotAPDF()
                    header_checked = True

            digest.update(chunk)
            fh.write(chunk)

        if total == 0:
            raise EmptyUpload()
        if not header_checked:
            raise NotAPDF()  # shorter than four bytes

        fh.close()
        return StagedUpload(path=tmp_path, sha256=digest.hexdigest(), size_bytes=total)

    except Exception:
        fh.close()
        tmp_path.unlink(missing_ok=True)
        raise


def storage_key(script_id: uuid.UUID) -> str:
    return f"{script_id}/original.pdf"


def resolve(upload_dir: str | Path, key: str) -> Path:
    return Path(upload_dir) / key


def commit(tmp_path: Path, upload_dir: str | Path, key: str) -> Path:
    """Move the validated temp file to its permanent home."""
    dest = resolve(upload_dir, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp_path, dest)
    return dest


def derive_title(filename: str | None) -> str:
    """Placeholder title taken from the filename.

    The real title comes off the title page once B4 can read document
    structure. Until then this keeps the NOT NULL column honest and gives
    the review UI something to render.
    """
    stem = Path(filename or "").stem.strip()
    cleaned = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return cleaned or "Untitled script"
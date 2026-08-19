"""Wire-format models.

These are the API's contract with the frontend. web/package.json runs

    openapi-typescript http://localhost:8080/openapi.json -o lib/api-types.ts

so whatever is declared here becomes the frontend's TypeScript verbatim.
Field names and nullability must match web/lib/api-types.ts exactly, or the
generated types silently stop matching the components that consume them.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel


class ScriptOut(BaseModel):
    """Mirrors the `Script` interface in web/lib/api-types.ts."""

    script_id: uuid.UUID
    title: str
    source_format: Literal["pdf", "fdx", "fountain"]
    page_count: int
    scene_count: int

    # No defaults on these two, deliberately. A Pydantic field with a
    # default is omitted from OpenAPI's `required` list, which makes
    # openapi-typescript emit `parse_warnings?: string[]` — optional, where
    # the frontend's hand-written interface says required. Every response
    # sets both explicitly, so requiring them costs nothing and keeps the
    # generated client honest.
    parse_warnings: list[str]

    # Non-null when this upload matched an existing script by SHA-256.
    # When set, `script_id` is that existing script — the caller gets the
    # original back rather than a second copy.
    duplicate_of: Optional[uuid.UUID]


class ApiErrorOut(BaseModel):
    """Mirrors `ApiError` in the frontend, plus a machine-readable `code`."""

    code: str
    detail: str


ERROR_RESPONSES: dict = {
    413: {"model": ApiErrorOut, "description": "File exceeds the 25 MB cap"},
    415: {"model": ApiErrorOut, "description": "Not a PDF"},
    422: {"model": ApiErrorOut, "description": "PDF could not be parsed"},
}
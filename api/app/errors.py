"""Uniform error bodies.

The frontend's contract (web/lib/api-types.ts) declares:

    interface ApiError          { detail: string }
    interface NoTextLayerError  { code: "NO_TEXT_LAYER"; pages_checked: number }

Both are **flat** objects. FastAPI's default HTTPException wraps whatever you
give it as {"detail": ...}, so a structured payload ends up nested one level
too deep and `body.code` reads as undefined in the browser. These handlers
emit the flat shape the client actually parses.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Raise this instead of HTTPException.

    `code` is the stable identifier the frontend switches on. `extra` fields
    are merged into the response body at the top level, which is how
    NoTextLayerError carries `pages_checked`.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        **extra: Any,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra
        super().__init__(detail)

    def body(self) -> dict:
        return {"code": self.code, "detail": self.detail, **self.extra}


async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flatten FastAPI's validation errors.

    By default these come back as {"detail": [ {...}, {...} ]} — an array,
    which does not satisfy `ApiError { detail: string }`. Collapse it to one
    readable sentence.
    """
    problems = exc.errors()
    first = problems[0] if problems else {}
    loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    msg = first.get("msg", "Invalid request.")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "detail": f"{loc}: {msg}" if loc else msg,
        },
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
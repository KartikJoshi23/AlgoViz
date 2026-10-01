"""
Problem details (RFC 9457)
==========================

Every error response is `application/problem+json`:

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "Strategy not found", "instance": "/api/v1/strategies/7",
     "request_id": "9f2c…"}

Validation failures add `errors` (one entry per invalid field). Unhandled
exceptions become a 500 whose detail never leaks the exception text; the
request id ties it to the server log. The OpenAPI document is rewritten to
match, so the generated client types describe what is actually sent.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from algoviz.core.middleware import request_id_var

logger = logging.getLogger("algoviz.http")

MEDIA_TYPE = "application/problem+json"


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[FieldError] | None = None  # validation failures only


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_body(
    status: int, detail: str | None = None, instance: str | None = None, **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"type": "about:blank", "title": _title(status), "status": status}
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    rid = request_id_var.get()
    if rid:
        body["request_id"] = rid
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def problem_response(
    status: int,
    detail: str | None = None,
    instance: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    return JSONResponse(
        problem_body(status, detail, instance, **extra),
        status_code=status,
        headers=headers,
        media_type=MEDIA_TYPE,
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        exc.status_code, detail, request.url.path, dict(exc.headers or {}) or None
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "loc": list(e.get("loc", ())),
            "msg": str(e.get("msg", "")),
            "type": str(e.get("type", "")),
        }
        for e in exc.errors()
    ]
    return problem_response(
        422,
        f"{len(errors)} invalid field{'s' if len(errors) != 1 else ''}",
        request.url.path,
        errors=errors,
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return problem_response(
        500,
        "An unexpected error occurred; the request id identifies it in the server log.",
        request.url.path,
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
    _document_problems(app)


def _document_problems(app: FastAPI) -> None:
    """Describe every error response as a Problem in the OpenAPI document (FastAPI's default 422 schema is not what is sent)."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["Problem"] = Problem.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        for name, sub in components["Problem"].pop("$defs", {}).items():
            components[name] = sub
        ref = {"$ref": "#/components/schemas/Problem"}
        for path_item in schema.get("paths", {}).values():
            for op in path_item.values():
                responses = op.get("responses", {})
                for code in list(responses):
                    if code.isdigit() and int(code) >= 400:
                        responses[code] = {
                            "description": responses[code].get("description") or _title(int(code)),
                            "content": {MEDIA_TYPE: {"schema": ref}},
                        }
                responses.setdefault(
                    "default",
                    {
                        "description": "Problem details (RFC 9457)",
                        "content": {MEDIA_TYPE: {"schema": ref}},
                    },
                )
        for unused in ("HTTPValidationError", "ValidationError"):
            components.pop(unused, None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Pydantic error types that mean "value outside allowed range".
_RANGE_TYPES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: Optional[list] = None, headers: Optional[dict] = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_response(status, code, message, details=None, headers=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


def _detail(err: dict) -> dict:
    """Turn a Pydantic error into {index, field, issue}. Never echoes the input value."""
    loc = [part for part in err["loc"] if part != "body"]
    index = None
    field = None
    if len(loc) >= 2 and loc[0] == "points" and isinstance(loc[1], int):
        index = loc[1]
        field = str(loc[2]) if len(loc) > 2 else "points"
    elif loc:
        field = str(loc[0])
    kind = err["type"]
    if kind in _RANGE_TYPES:
        issue = "out_of_range"
    elif kind == "extra_forbidden":
        issue = "unknown_field"
    else:
        issue = kind
    return {"index": index, "field": field, "issue": issue}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(e["type"] == "json_invalid" for e in errors):
            return error_response(400, "bad_request", "Malformed JSON body")
        return error_response(422, "validation_error", "Request validation failed",
                              [_detail(e) for e in errors])

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = exc.detail if isinstance(exc.detail, str) else "http_error"
        code = code.lower().replace(" ", "_")
        return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

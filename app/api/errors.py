"""Exception handlers for QueueStorm Investigator (T009).

Maps:
  - RequestValidationError (body-level) → 400 Bad Request
  - RequestValidationError (field-level) → 422 Unprocessable Entity
  - Exception (fallback) → 500 Internal Server Error
Ensures no sensitive data or stack traces are leaked (AC-13).
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY, HTTP_500_INTERNAL_SERVER_ERROR


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = exc.errors()
        for error in errors:
            loc = error.get("loc", ())
            err_type = error.get("type", "")
            # If the error is at the top-level 'body' (e.g., malformed JSON syntax,
            # empty body, or JSON that is a list/string instead of a dict object),
            # return 400 Bad Request.
            # Malformed JSON syntax error in Pydantic v2 has loc=('body', <int index>) and type='json_invalid'.
            is_body_level = (
                loc == ("body",)
                or err_type == "json_invalid"
                or (len(loc) > 1 and loc[0] == "body" and isinstance(loc[1], int))
            )
            if is_body_level:
                return JSONResponse(
                    status_code=HTTP_400_BAD_REQUEST,
                    content={"detail": "Malformed JSON or invalid body structure."}
                )
        
        # Field-level errors (missing required fields, or semantic/value validation
        # like empty complaint strings) return 422.
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(errors)}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        # Pass through standard HTTP status codes (e.g., 404, 405)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    @app.exception_handler(Exception)
    async def internal_server_error_handler(request, exc: Exception):
        # Fallback for unexpected errors: return 500 Internal Server Error
        # without leaking any stack trace, file path, or secrets.
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."}
        )

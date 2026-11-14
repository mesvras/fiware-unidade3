from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .convert import ConversionError
from .orion import OrionError, OrionUnavailable
from .validation import ValidationFailed


class ApiError(Exception):
    def __init__(self, status: int, *errors: str):
        self.status = status
        self.errors = list(errors)


def not_found(what: str) -> ApiError:
    return ApiError(404, f"{what} não encontrado")


def register(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError):
        return JSONResponse(status_code=e.status, content={"errors": e.errors})

    @app.exception_handler(ConversionError)
    @app.exception_handler(ValidationFailed)
    async def invalid(_: Request, e):
        return JSONResponse(status_code=400, content={"errors": e.errors})

    @app.exception_handler(OrionError)
    async def orion_error(_: Request, e: OrionError):
        if e.status == 409:
            return JSONResponse(status_code=409, content={"errors": ["registro já existe"]})
        return JSONResponse(status_code=502, content={"errors": [f"Orion-LD respondeu {e.status}"]})

    @app.exception_handler(OrionUnavailable)
    async def unavailable(_: Request, e: OrionUnavailable):
        return JSONResponse(status_code=503, content={"errors": ["Orion-LD indisponível"]})

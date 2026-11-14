from fastapi import Request

from .auth import Principal
from .orion import Orion


def get_orion(request: Request) -> Orion:
    return request.app.state.orion


def current_principal(request: Request) -> Principal:
    return request.state.principal


def current_owner(request: Request) -> str:
    return request.state.principal.owner

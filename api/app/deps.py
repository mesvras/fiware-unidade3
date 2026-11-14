from fastapi import Request

from .config import settings
from .orion import Orion


def get_orion(request: Request) -> Orion:
    return request.app.state.orion


def current_owner() -> str:
    return settings.dev_owner

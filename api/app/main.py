from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import errors
from .config import settings
from .orion import Orion, OrionUnavailable
from .routers import availability, hotels


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.orion = Orion(settings)
    yield
    await app.state.orion.close()


app = FastAPI(title="API da plataforma de turismo e cultura de Natal", version="0.1.0", lifespan=lifespan)
errors.register(app)
app.include_router(hotels.router)
app.include_router(availability.router)


@app.get("/health")
async def health():
    try:
        version = await app.state.orion.version()
    except OrionUnavailable as e:
        return JSONResponse(status_code=503, content={"status": "unavailable", "orion": str(e)})
    return {"status": "ok", "orion": version}

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from . import errors
from .auth import Verifier, authenticate, writer
from .config import settings
from .orion import Orion, OrionUnavailable
from .routers import availability, beaches, events, hotels, stations, venues

class StripQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            record.args = (*record.args[:2], record.args[2].split("?", 1)[0], *record.args[3:])
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("uvicorn.access").addFilter(StripQuery())
log = logging.getLogger("app")

ROUTES = (
    (hotels.router, "hotelaria"),
    (availability.router, None),
    (venues.restaurants, "bares-restaurantes"),
    (venues.bars, "bares-restaurantes"),
    (events.router, "produtor-cultural"),
    (beaches.router, "gestor-governo"),
    (stations.sampling_points, "gestor-governo"),
    (stations.weather_stations, "gestor-governo"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.problems()
    if problems:
        raise RuntimeError("configuração de autenticação insegura ou incompleta: " + "; ".join(problems))
    if not settings.auth_enabled:
        log.warning("AUTENTICAÇÃO DESLIGADA (AUTH_ENABLED=false): use só em desenvolvimento")
    app.state.orion = Orion(settings)
    app.state.verifier = Verifier(settings)
    yield
    await app.state.verifier.close()
    await app.state.orion.close()


docs = {} if not settings.auth_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="API da plataforma de turismo e cultura de Natal", version="0.1.0", lifespan=lifespan, **docs)
errors.register(app)
for router, role in ROUTES:
    app.include_router(router, dependencies=[Depends(authenticate), *([Depends(writer(role))] if role else [])])


@app.get("/health")
async def health():
    try:
        version = await app.state.orion.version()
    except OrionUnavailable as e:
        detail = {} if settings.auth_enabled else {"orion": str(e)}
        return JSONResponse(status_code=503, content={"status": "unavailable", **detail})
    return {"status": "ok", **({} if settings.auth_enabled else {"orion": version})}

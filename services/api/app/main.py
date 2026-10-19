import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .db import lifespan

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="LogWatch API",
    version="0.1.0",
    description=(
        "Read API over LogWatch telemetry. Serves aggregate statistics and "
        "per-trace detail for programmatic consumers. Prompt and SQL text are "
        "never exposed: response models carry hashes and fingerprints only."
    ),
    lifespan=lifespan,
)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict:
    """Is the process alive? No dependencies checked, so this stays cheap."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], summary="Readiness probe")
async def ready(request: Request) -> JSONResponse:
    """Can we actually serve traffic? Checks that Postgres responds."""
    try:
        async with request.app.state.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 AS ok")
                await cur.fetchone()
        return JSONResponse({"status": "ready", "database": "ok"})
    except Exception as exc:
        logging.getLogger(__name__).warning("readiness check failed: %s", exc)
        return JSONResponse(
            {"status": "not ready", "database": "unreachable"},
            status_code=503,
        )

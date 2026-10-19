import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the connection pool at startup, close it at shutdown."""
    settings = get_settings()
    pool = AsyncConnectionPool(
        conninfo=settings.dsn,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=True, timeout=30)
    app.state.pool = pool
    logger.info("connection pool opened")

    yield

    await pool.close()
    logger.info("connection pool closed")


def get_pool(app: FastAPI) -> AsyncConnectionPool:
    return app.state.pool

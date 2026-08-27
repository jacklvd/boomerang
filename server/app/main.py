"""FastAPI application entrypoint.

Wires the ASGI app and its cold-start lifespan. Route modules live under ``app.routes``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import bedrock


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run cold-start work once per container, before the first request is served."""
    # dev-note: this runs on Lambda cold start, because the ASGI adapter is configured with
    # lifespan handling on. Anything cached for the warm lifetime of the container belongs
    # here — model config validation now, SSM credential fetch when USPS lands. If lifespan
    # is ever turned off, none of it runs and the cache is silently never populated.
    bedrock.verify_config()
    yield


app = FastAPI(title="boomerang", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Deliberately does no I/O, so it stays honest about the process only."""
    return {"status": "ok"}

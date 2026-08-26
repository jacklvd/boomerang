from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import bedrock


@asynccontextmanager
async def lifespan(app: FastAPI):
    # dev-note: this runs on Lambda cold start, because the ASGI adapter is configured with
    # lifespan handling on. Anything cached for the warm lifetime of the container belongs
    # here — model config validation now, SSM credential fetch when USPS lands. If lifespan
    # is ever turned off, none of it runs and the cache is silently never populated.
    bedrock.verify_config()
    yield


app = FastAPI(title="boomerang", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}

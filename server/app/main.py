from fastapi import FastAPI

from app.api.v1.receipts import router as receipts_router

app = FastAPI(title="boomerang")
app.include_router(receipts_router)


@app.get("/health")
def health():
    return {"status": "ok"}

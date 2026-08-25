from fastapi import FastAPI

app = FastAPI(title="boomerang")


@app.get("/health")
def health():
    return {"status": "ok"}

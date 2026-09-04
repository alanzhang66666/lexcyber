from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.routers import cases, documents, reviews, skills, tasks
from storage.postgres.repository import init_db
from storage.redis import configure_broker


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception:
        pass
    try:
        configure_broker()
    except Exception:
        pass
    yield


app = FastAPI(title="Lex Multi-Agent Backend", version="0.2.0", lifespan=lifespan)
app.include_router(tasks.router)
app.include_router(skills.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(reviews.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-api", "version": "0.2.0"}

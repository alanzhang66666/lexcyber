from fastapi import FastAPI

from config.settings import settings
from retrieval.gateway import RetrievalGateway
from retrieval.schemas import RetrievalQuery

app = FastAPI(title="Lex Retrieval Gateway", version="0.1.0")
gateway = RetrievalGateway()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-retrieval-gateway", "backend_configured": bool(settings.knowledge_base_url)}


@app.post("/retrieval/search")
def search(query: RetrievalQuery):
    return gateway.search(query)

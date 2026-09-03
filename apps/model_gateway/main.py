from fastapi import FastAPI

from models.gateway import ModelGateway
from models.schemas import ModelRequest

app = FastAPI(title="Lex Model Gateway", version="0.1.0")
gateway = ModelGateway()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-model-gateway", "provider": gateway.router.primary.provider}


@app.post("/v1/invoke")
def invoke(request: ModelRequest):
    return gateway.invoke(request)

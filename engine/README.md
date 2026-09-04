# LexCyber execution engine

`engine/` is an internal Python boundary. It owns LangGraph execution, Skill Runtime calls, model access and durable execution records in the `engine` schema. The browser and Java public API never call this package directly.

Run locally after PostgreSQL/Redis are available:

```bash
uvicorn engine.api:app --host 0.0.0.0 --port 8100
dramatiq engine.api --processes 1 --threads 4
```

Every internal request requires `X-Service-Token`. Persistence failures return an explicit `503`; the engine does not fabricate a successful result or an in-memory review id.

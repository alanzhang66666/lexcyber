# LexCyber execution engine

`engine/` is an internal Python boundary. It owns LangGraph execution, Skill Runtime calls, model access and durable execution records in the `engine` schema. The browser and Java public API never call this package directly.

Run locally after PostgreSQL/Redis are available:

```bash
WORKFLOW_PROFILE=stub uvicorn engine.run_api_v03:app --host 0.0.0.0 --port 8100
WORKFLOW_PROFILE=stub dramatiq engine.run_api_v03 --processes 1 --threads 4
```

Every internal request requires `X-Service-Token`. Persistence failures return an explicit `503`; the engine does not fabricate a successful result or an in-memory review id.

When `metadata.taskType` is `document.parse`, the worker loads stored file bytes from MinIO and runs the PDF/DOCX parse skills. `model.probe` calls ModelGateway. `sentencing.calculate` routes to the T3 `SentencingRunner` but stays gated: while `SENTENCING_ENABLED=false` it fails with `SENTENCING_UNAVAILABLE`, and unapproved rules return a `blocked` result that parks the task in `waiting_review`. Other tasks still use `WORKFLOW_PROFILE` (`stub` by default).

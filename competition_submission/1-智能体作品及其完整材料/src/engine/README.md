# LexCyber execution engine

`engine/` is an internal Python boundary. It owns LangGraph execution, Skill Runtime calls, model access and durable execution records in the `engine` schema. The browser and Java public API never call this package directly.

The competition image uses the `case.assist.analyze` runner for the complete
material → extraction → local knowledge retrieval → DeepSeek → deterministic
verification → human review path. The runner refuses the stub provider unless
an explicit test-only `ALLOW_STUB_MODEL=true` is set.

Run locally after PostgreSQL/Redis are available:

```bash
WORKFLOW_PROFILE=competition uvicorn engine.run_api_v03:app --host 0.0.0.0 --port 8100
WORKFLOW_PROFILE=competition dramatiq engine.run_api_v03 --processes 1 --threads 2
```

Every internal request requires `X-Service-Token`. Persistence failures return an explicit `503`; the engine does not fabricate a successful result or an in-memory review id.

When `metadata.taskType` is `document.parse`, the worker loads stored file bytes from the configured object store and runs the PDF/DOCX parse skills. `case.assist.analyze` invokes the bounded competition workflow. `model.probe` calls ModelGateway. `sentencing.calculate` remains a separate gated adapter and is not part of the competition success path.

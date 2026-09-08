# Model probe record

- recordedAt: 2026-09-08T09:15:00Z
- status: blocked
- reason: `MODEL_API_KEY` is unset and `MODEL_PROVIDER=stub` in `.env.v03`.
- script: `scripts/model-probe.ps1` was not run against Compose.

This is not a real model call. A stub / `WORKFLOW_PROFILE=stub` result must not be recorded as a live probe.

To record a real call later:

1. Set a non-stub `MODEL_PROVIDER` and `MODEL_API_KEY` (optional `MODEL_API_BASE_URL`, `MODEL_TIMEOUT_SECONDS`).
2. Recreate the engine / worker with those values. Do not change the default `WORKFLOW_PROFILE=stub` in repo examples unless the probe run itself needs a non-stub profile.
3. Run `scripts/model-probe.ps1` and replace this file with the script output.

Do not store API keys in this file.

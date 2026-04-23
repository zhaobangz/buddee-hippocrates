# Tracing Setup Guide (OpenTelemetry)

Buddi emits tracing spans via OpenTelemetry to an OTLP HTTP endpoint.

## Current implementation points

- `core/tracing.py`
  - Initializes a tracer provider once
  - Configures OTLP exporter to `http://localhost:4318/v1/traces`
- `backend/api.py`
  - Startup span (`system_startup`)
  - FHIR ingest span (`process_fhir_bundle`) with payload-size attributes
- `core/agent.py`
  - Top-level orchestration span (`agent_handle`)
  - Intent detection + task-specific spans
  - PHI-safe telemetry posture (payload hashes/sizes, no raw PHI fields)

## Local trace viewing workflow

1. Start an OTLP-compatible collector (for example VS Code Trace Viewer collector on port `4318`).
2. Run Buddi backend:

```bash
python start.py
```

3. Trigger API calls (for example `POST /ingest/fhir`).
4. Inspect spans in your trace viewer.

## Example span attributes you should see

- `payload_size_bytes`
- `payload_hash`
- `detected_intent`
- `rag_docs_found`
- `note_size_bytes` (FHIR path)

## Adding custom spans

```python
from core.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("my_operation") as span:
    span.set_attribute("component", "my-module")
    # work
```

## Notes

- If no collector is listening on `localhost:4318`, tracing export may fail silently/non-fatally depending on runtime.
- `shutdown_tracing()` is currently a stub; graceful flush behavior can be expanded later if needed.

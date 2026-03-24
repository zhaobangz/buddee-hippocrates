# clinical Tracing Setup Guide

Tracing is integrated into the Buddi Clinical Agent using OpenTelemetry. This provides oversight and a detailed audit trail of all clinical activities and tool executions.

## Integrated Components

### 1. **Core Tracing** (`core/tracing.py`)
- Initializes OpenTelemetry with an OTLP HTTP exporter.
- Targets `localhost:4318` by default (compatible with VS Code Trace Viewer).
- Provides simple hooks for adding precision tracing to new clinical tools.

### 2. **Backend API Tracing** (`backend/api.py`)
- Every chat request and patient context change is captured in a trace span.
- Attributes include input length and processing performance.

### 3. **Clinical Tool Tracing** (`core/agent.py`)
- Tracks the decision logic as the orchestrator routes to specific tools:
  - **EHR Reader** (Clinical PDF parsing)
  - **Prior Auth** (Insurance form generation)
  - **Guidelines** (Medical reference lookups)
  - **Follow-Up & Scheduling** (Care coordination)

## How to View Traces

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start the Trace Collector
In VS Code, run the command:
`AI Toolkit: Open Trace Viewer`
This starts the OTLP collector on `localhost:4318`.

### Step 3: Run the Agent
```bash
./run-web-dev.sh
```

### Step 4: Analyze Clinical Spans
As you interact with the agent, the Trace Viewer will show:
- **Timeline**: How long each clinical tool took to execute.
- **Metadata**: Targeted patient ID, identified intent, and safety validation flags.
- **Errors**: Detailed stack traces within the clinical context for easier debugging.

## Adding Custom Traces

To trace a new clinical tool or function:
```python
from core.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("clinical_tool_name") as span:
    span.set_attribute("patient_id", "12345")
    # Your tool logic here
```

---

**Status**: ✅ Automated Clinical Tracing Integrated | ✅ Tool-Level Granularity

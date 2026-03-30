# Clinical Tracing Setup Guide

Tracing is deeply integrated into the Buddi Clinical Agent using OpenTelemetry. This provides real-time oversight and a forensic audit trail of all AI-driven clinical activities, tool executions, and RAG grounding steps.

## 🏥 Integrated Components

### 1. **Terminal Tracing** (`core/tracing.py`)
- Initializes OpenTelemetry with an OTLP HTTP exporter.
- Targets `localhost:4318` by default (compatible with VS Code Trace Viewer).
- Provides simple hooks for adding precision tracing to new clinical workflow segments.

### 2. **Backend API Tracing** (`backend/api.py`)
- Every chat interaction, **Risk Assessment**, and **Shadow Mode comparison** is captured in a dedicated trace span.
- Attributes include input length, processing latency, and detected clinical intent.

### 3. **Intelligence Tracing** (`core/rag_engine.py` & `core/agent.py`)
- **RAG Latency**: Measures vector search performance against the FAISS clinical index.
- **Tool Orchestration**: Tracks the decision logic as the agent routes between:
  - **EHR Reader** (Clinical PDF parsing)
  - **Prior Auth** (Insurance form generation)
  - **Guidelines** (Medical reference lookups)
  - **Care Coordination** (Scheduling & Follow-ups)

## 📡 How to Monitor Traces

### Step 1: Initialize Environment
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Activate Trace Collector
In VS Code, run the command:
`AI Toolkit: Open Trace Viewer`
This starts the OTLP collector on **port 4318**.

### Step 3: Launch the Integrated Agent
```bash
chmod +x run-web.sh
./run-web.sh
```

### Step 4: Analyze Clinical Spans
As you interact with the dashboard, the Trace Viewer will show:
- **Timeline**: How long each clinical tool and RAG search took to execute.
- **Metadata**: Targeted patient ID, identified intent, and safety validation flags.
- **Grounding**: The specific guideline documents retrieved by the RAG engine during reasoning.

## 🛠 Adding Custom Spans

To trace a new clinical tool or high-performance segment:
```python
from core.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("clinical_tool_name") as span:
    span.set_attribute("patient_id", "12345")
    # Your clinical logic here
```

---

**Status**: ✅ **Grounding Spans Active**. Buddi provides full clinical observability from the UI terminal down to the vector search logic.

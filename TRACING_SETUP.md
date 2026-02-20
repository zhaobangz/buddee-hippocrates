# Tracing Setup Guide

Tracing has been successfully added to your Buddi AI Agent project using OpenTelemetry. This guide explains what was set up and how to use it.

## What Was Added

### 1. **Dependencies** (requirements.txt)
Added OpenTelemetry packages for distributed tracing:
- `opentelemetry-api` - Core tracing API
- `opentelemetry-sdk` - SDK implementation
- `opentelemetry-exporter-otlp` - OTLP HTTP exporter
- `opentelemetry-instrumentation` - Base instrumentation
- `opentelemetry-instrumentation-requests` - Automatic HTTP request tracing

### 2. **Tracing Configuration** (core/tracing.py)
New module that:
- Initializes OpenTelemetry with OTLP exporter pointing to AI Toolkit's localhost:4318
- Provides `setup_tracing()` to initialize the tracer provider
- Provides `get_tracer()` to get tracers for any module
- Provides `shutdown_tracing()` for graceful cleanup

### 3. **Main Entry Point Instrumentation** (main.py)
- Calls `setup_tracing()` at startup
- Wraps `main()` function in a span
- Tracks user input handling with span attributes
- Calls `shutdown_tracing()` on exit to flush all spans

### 4. **Agent Class Instrumentation** (core/agent.py)
Traces key operations:
- `detect_intent()` - Intent classification with input/output details
- `handle()` - Main request processing with detailed spans for:
  - File organization tasks
  - Website opening
  - Web searches
  - System commands
  - General queries

## How to Use

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start the Trace Collector
In VS Code, run the command:
```
AI Toolkit: Open Trace Viewer
```
This starts the OTLP collector on localhost:4318 and opens the trace viewer.

### Step 3: Run Your Agent
```bash
python main.py
```

### Step 4: View Traces
Interact with the agent through text or voice input. Every action will generate traces visible in the AI Toolkit's Trace Viewer showing:
- Request processing timeline
- Intent detection spans
- Tool execution (file operations, web searches, etc.)
- Response generation timing
- Attributes like input length, detected intent, target folders, etc.

## Key Tracing Points

The agent now traces:
- **Main request flow**: Full span for user input handling
- **Intent detection**: What the user is trying to do
- **File operations**: Organization attempts with target folder and strategy
- **Web interactions**: Searches and website opens with URLs/queries
- **LLM calls**: Response generation timing
- **Errors**: Exception details captured in spans

## Customization

To add more tracing to specific functions, use:
```python
from core.tracing import get_tracer

tracer = get_tracer(__name__)

# In your function
with tracer.start_as_current_span("operation_name") as span:
    span.set_attribute("key", "value")
    # Your code here
```

## OTLP Endpoint Configuration

Default: `http://localhost:4318`

To use a different endpoint, set the environment variable:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-endpoint:4318
```

## Performance Impact

- Minimal overhead from trace collection
- Spans are batched and exported asynchronously
- No blocking of main request processing
- Graceful shutdown ensures all spans are flushed before exit

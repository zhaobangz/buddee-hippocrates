"""
Buddi Tracing System — OpenTelemetry Integration
Provides clinical observability and audit forensic trails.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

_tracer_initialized = False

def setup_tracing(service_name="buddi-clinical-agent"):
    global _tracer_initialized
    if _tracer_initialized:
        return
        
    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    
    # 1. Console Exporter (for debugging)
    # processor = BatchSpanProcessor(ConsoleSpanExporter())
    # provider.add_span_processor(processor)
    
    # 2. OTLP Exporter (for VS Code Trace Viewer)
    try:
        otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
        otlp_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(otlp_processor)
    except Exception as e:
        print(f"Tracing: OTLP Exporter failed to initialize: {e}")

    trace.set_tracer_provider(provider)
    _tracer_initialized = True

def get_tracer(name):
    return trace.get_tracer(name)

def shutdown_tracing():
    # Optional: flush and shutdown the tracer
    pass

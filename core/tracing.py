"""
Buddi Tracing System — OpenTelemetry Integration
Provides clinical observability and audit forensic trails.
"""
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
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
    
    # 2. OTLP Exporter (optional for local trace viewer / production collector).
    # Do not default to localhost:4318: if no collector is running, the exporter
    # emits noisy connection errors during tests and local demos.
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if otlp_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
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

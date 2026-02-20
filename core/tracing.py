"""
OpenTelemetry tracing setup for the AI Agent application.
This module initializes distributed tracing using OpenTelemetry SDK.
"""

import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Configure resource information for traces
def setup_tracing(service_name: str = "buddi-agent", 
                  otlp_endpoint: str = None) -> TracerProvider:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service for tracing
        otlp_endpoint: OTLP exporter endpoint (defaults to AI Toolkit's localhost:4318)
    
    Returns:
        Configured TracerProvider instance
    """
    if otlp_endpoint is None:
        # Default to AI Toolkit's OTLP HTTP endpoint
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    
    # Create resource attributes
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
    })
    
    # Initialize tracer provider
    tracer_provider = TracerProvider(resource=resource)
    
    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    # Set the global tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    # Instrument the requests library for automatic HTTP tracing
    RequestsInstrumentor().instrument()
    
    return tracer_provider


def get_tracer(module_name: str) -> trace.Tracer:
    """
    Get a tracer instance for a specific module.
    
    Args:
        module_name: Name of the module requesting the tracer
    
    Returns:
        Tracer instance for the module
    """
    return trace.get_tracer(module_name)


def shutdown_tracing() -> None:
    """
    Gracefully shutdown the tracing provider.
    Call this at application exit to ensure all spans are exported.
    """
    try:
        trace_provider = trace.get_tracer_provider()
        if hasattr(trace_provider, 'force_flush'):
            trace_provider.force_flush(timeout_millis=5000)
        if hasattr(trace_provider, 'shutdown'):
            trace_provider.shutdown()
    except Exception as e:
        print(f"Error during tracing shutdown: {e}")

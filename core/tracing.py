"""
OpenTelemetry tracing setup for the AI Agent application.
This module initializes distributed tracing using OpenTelemetry SDK.
"""

import os
from opentelemetry import trace  # type: ignore
from opentelemetry.sdk.trace import TracerProvider  # type: ignore
from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
from opentelemetry.sdk.resources import Resource  # type: ignore
from opentelemetry.instrumentation.requests import RequestsInstrumentor  # type: ignore

# Configure resource information for traces
def setup_tracing(service_name: str = "buddi-agent", 
                  otlp_endpoint: str | None = None) -> TracerProvider:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service for tracing
        otlp_endpoint: OTLP exporter endpoint (defaults to AI Toolkit's localhost:4318)
    
    Returns:
        Configured TracerProvider instance
    """
    print("--- Initializing OpenTelemetry Tracing ---")
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
    
    # Extract hostname and port safely
    host = otlp_endpoint.replace("http://", "").replace("https://", "").split("/")[0]
    hostname, _, port_str = host.partition(':')
    port = int(port_str) if port_str else 80
    
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        if result == 0:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        else:
            print(f"⚠ Tracing collector not found at {otlp_endpoint} (Silently dropping spans).")
    except Exception:
        print(f"⚠ Tracing disabled: Could not verify endpoint {otlp_endpoint}.")
    
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


def create_custom_span(tracer: trace.Tracer):
    """
    This is an example function to demonstrate how to create a custom span.
    A span represents a unit of work or an operation.

    Args:
        tracer: The tracer instance to use for creating the span.
    """
    with tracer.start_as_current_span("custom_span_name") as span:
        # You can add attributes to the span
        span.set_attribute("custom_attribute_key", "custom_attribute_value")
        # You can also add events to the span
        span.add_event("This is a custom event.")
        # The code inside this block is now being traced as part of "custom_span_name"
        print("This code is inside a custom span.")


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


# Example of how to use the tracing functions.
# This part is for demonstration and would typically be in your main application logic.
if __name__ == "__main__":
    # 1. Set up tracing
    tracer_provider = setup_tracing()

    # 2. Get a tracer for your module
    tracer = get_tracer(__name__)

    # 3. Create a custom span
    create_custom_span(tracer)

    print("Custom span created. Check your OpenTelemetry backend to see the trace.")

    # 4. Shutdown tracing when your application exits
    shutdown_tracing()

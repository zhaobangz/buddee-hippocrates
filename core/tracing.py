"""
Buddi Tracing System — OpenTelemetry Integration
Provides clinical observability and audit forensic trails.

Import safety
-------------
OpenTelemetry's API / SDK / exporter / instrumentation packages are version-
coupled; a partial install or a version skew makes the top-level imports raise
``ImportError`` (or, on skew, ``AttributeError``). Because ``backend/api.py``
and ``core/agent.py`` import this module at startup, a tracing import failure
used to take the whole app — and the test suite — down with it.

This module now degrades cleanly: if OpenTelemetry cannot be imported, tracing
becomes a no-op (``get_tracer`` returns a tracer whose spans do nothing) and
the rest of the application runs unaffected. This is the desired behaviour in
test mode and in any deployment that simply has not provisioned a collector.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Probe only the lightweight, stable API package at import time. The heavier
# SDK/exporter packages (the ones most likely to version-skew) are imported
# lazily inside setup_tracing(), so an SDK problem degrades to a no-op rather
# than failing this module's import.
try:
    from opentelemetry import trace

    _OTEL_AVAILABLE = True
    _OTEL_IMPORT_ERROR: Exception | None = None
except (ImportError, AttributeError) as exc:  # version skew
    trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False
    _OTEL_IMPORT_ERROR = exc

_tracer_initialized = False


class _NoopSpan:
    """A span that supports the methods Buddi actually calls, but does nothing.

    Mirrors the subset of the OpenTelemetry ``Span`` API used across
    ``backend/api.py`` and ``core/agent.py`` (context-manager + ``set_attribute``
    / ``set_status`` / ``record_exception`` / ``add_event``), so call sites need
    no ``if tracing_enabled`` guards.
    """

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_exc_info) -> bool:
        return False  # never suppress exceptions

    def set_attribute(self, *_args, **_kwargs) -> None:
        pass

    def set_status(self, *_args, **_kwargs) -> None:
        pass

    def record_exception(self, *_args, **_kwargs) -> None:
        pass

    def add_event(self, *_args, **_kwargs) -> None:
        pass

    def end(self, *_args, **_kwargs) -> None:
        pass


class _NoopTracer:
    def start_as_current_span(self, *_args, **_kwargs) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, *_args, **_kwargs) -> _NoopSpan:
        return _NoopSpan()


_NOOP_TRACER = _NoopTracer()


def setup_tracing(service_name: str = "buddi-clinical-agent") -> None:
    """Initialise the OTLP exporter once, if OpenTelemetry is available.

    No-op (with a single warning) when OpenTelemetry is not importable, or when
    no ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is configured.
    """
    global _tracer_initialized
    if _tracer_initialized:
        return

    if not _OTEL_AVAILABLE or trace is None:
        logger.warning(
            "OpenTelemetry unavailable (%s); tracing disabled (no-op spans).",
            _OTEL_IMPORT_ERROR,
        )
        _tracer_initialized = True
        return

    # Import the SDK/exporter lazily: these are the packages most prone to
    # version skew, and a failure here should disable tracing, not crash boot.
    try:
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("OpenTelemetry SDK unavailable (%s); tracing disabled.", exc)
        _tracer_initialized = True
        return

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    # OTLP Exporter (optional for local trace viewer / production collector).
    # Do not default to localhost:4318: if no collector is running, the exporter
    # emits noisy connection errors during tests and local demos.
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except (ImportError, ValueError) as exc:
            logger.warning("Tracing: OTLP exporter failed to initialize: %s", exc)

    trace.set_tracer_provider(provider)
    _tracer_initialized = True


def get_tracer(name: str):
    """Return a tracer. Never raises — falls back to a no-op tracer.

    When OpenTelemetry is available this returns a real tracer (which itself
    no-ops until a provider is configured by ``setup_tracing``); otherwise it
    returns the in-module no-op tracer so call sites work unchanged.
    """
    if not _OTEL_AVAILABLE or trace is None:
        return _NOOP_TRACER
    try:
        return trace.get_tracer(name)
    except (ValueError, AttributeError) as exc:
        logger.warning("get_tracer(%s) failed (%s); using no-op tracer.", name, exc)
        return _NOOP_TRACER


def shutdown_tracing() -> None:
    # Optional: flush and shutdown the tracer. BatchSpanProcessor flushes on
    # provider shutdown; nothing required for the no-op path.
    pass

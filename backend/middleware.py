"""Starlette middleware for Buddi backend.

Provides two ASGI middlewares that ``backend/api.py`` wires in at app
construction:

  * ``RequestIDMiddleware`` — assigns a stable UUID to every incoming
    request, exposes it on ``request.state.request_id`` and as an
    ``X-Request-ID`` response header. Used by structured logging, audit
    persistence, and operator-UI error reporting.
  * ``RateLimitMiddleware`` — per-client token bucket backed by Redis
    via the ``slowapi`` library. The bucket is keyed by tenant UUID when
    the request is authenticated, falling back to a trusted-XFF or
    socket-peer IP. Because the counters live in Redis they are shared
    across every Cloud Run revision, which closes the
    ``effective_limit = N × configured_limit`` hole called out in the
    strategic manual (§4.2 Bottleneck #1).

Configuration:

  * ``REDIS_URL`` — connection string for the limiter backend. Defaults
    to ``redis://localhost:6379/0`` for local dev. Production MUST point
    at GCP Memorystore inside our private VPC (manual §4.2: "Run
    Memorystore (GCP-managed Redis) in private VPC, not a self-hosted
    Redis").
  * ``BUDDI_RATE_LIMIT_DISABLED=1`` — short-circuits the limiter for
    CI / unit tests (see ``.github/workflows/main.yml``).
  * ``TRUSTED_PROXY_CIDRS`` — comma-separated networks whose
    ``X-Forwarded-For`` header we trust as the client identity.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Tuple

from fastapi.responses import JSONResponse
from limits import parse as parse_rate_limit
from slowapi import Limiter as SlowAPILimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a UUID we can correlate across logs / audit.

    If the upstream client provides ``X-Request-ID`` we honour it (so a
    customer's reverse proxy can pin a trace ID end-to-end). Otherwise we
    generate a fresh UUID4. Either way the resolved ID lands on
    ``request.state.request_id`` and is echoed back on the response.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        # Reject overlong or non-printable IDs — a malicious value would
        # otherwise show up verbatim in our structured logs / audit rows.
        if incoming and 0 < len(incoming) <= 128 and all(ch.isprintable() for ch in incoming):
            request_id = incoming
        else:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


# ---------------------------------------------------------------------------
# Rate limiter (Redis-backed, via slowapi)
# ---------------------------------------------------------------------------

# Production must point this at GCP Memorystore inside our private VPC.
# A self-hosted Redis on a public IP is explicitly out of scope per the
# strategic manual (§4.2 Bottleneck #1).
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


@dataclass
class RateLimitConfig:
    """Tunable defaults for the rate limiter.

    The numbers are deliberately conservative — see
    ``Buddi_Strategic_Founders_Operating_Manual.pdf §4.2`` for the
    capacity-planning notes behind the Redis-backed implementation.
    """

    #: Requests permitted in ``window_seconds`` per client identity.
    requests_per_window: int = 30
    window_seconds: float = 60.0

    #: Paths that are exempt from rate limiting (health probes, signed-
    #: roots listing for ops, etc.).
    exempt_path_prefixes: Tuple[str, ...] = (
        "/health",
        "/internal/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    #: H-1: LLM/cost-heavy route prefixes. When the limiter backend errors
    #: repeatedly these paths fail CLOSED (429) instead of open, so a Redis
    #: outage cannot turn into unbounded LLM spend and worker backlog. Cheap
    #: paths keep failing open to preserve availability.
    #: ``/api/auth`` is included for a different reason: credential endpoints
    #: are the highest-value brute-force target on the internet surface, so
    #: their limiter must never silently drop open.
    expensive_path_prefixes: Tuple[str, ...] = (
        "/api/shadow",
        "/shadow",
        "/api/prior-auth",
        "/prior-auth",
        "/api/ingest",
        "/ingest",
        "/api/fhir",
        "/api/chat",
        "/chat",
        "/api/auth",
    )

    #: Consecutive storage errors before expensive paths fail closed.
    max_consecutive_storage_errors: int = 3

    #: Redis storage URI. ``None`` means resolve from ``REDIS_URL`` env at
    #: middleware construction (the normal production path); tests pass an
    #: explicit value to point at a fakeredis instance.
    storage_uri: Optional[str] = None


def _trusted_proxy_cidrs() -> Tuple[ipaddress.IPv4Network, ...]:
    """Parse the ``TRUSTED_PROXY_CIDRS`` env into a tuple of networks.

    Only IPs inside these networks may have their ``X-Forwarded-For``
    header trusted as the client identity. Anything outside is identified
    by the connecting socket peer — preventing an attacker from spoofing
    a fresh bucket per request by setting an arbitrary XFF header.
    """

    raw = os.getenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    networks = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            networks.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            logger.warning("Ignoring malformed TRUSTED_PROXY_CIDRS entry: %s", chunk)
    return tuple(networks)


def validate_trusted_proxy_cidrs() -> Tuple[ipaddress.IPv4Network, ...]:
    """Startup guard for ``TRUSTED_PROXY_CIDRS`` (Issue 8).

    Parsing is lenient (malformed entries are dropped with a warning), so a
    typo or an empty value can silently collapse the trusted set to zero
    networks. With zero trusted networks, ``_client_identity`` never honours
    ``X-Forwarded-For`` — which is the safe default for a direct-to-internet
    deployment, but a *misconfiguration* behind a real proxy where an
    attacker could otherwise spoof XFF to mint a fresh rate-limit bucket per
    request. Rather than boot a non-development process in that ambiguous
    state, we fail closed.

    Returns the parsed networks. Logs the resolved set at INFO. Raises
    ``ValueError`` when the set is empty and ``ENVIRONMENT`` is not
    ``development``.
    """

    cidrs = _trusted_proxy_cidrs()
    logger.info("Trusted proxy CIDRs: %s", [str(n) for n in cidrs])
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
    world = [n for n in cidrs if n.prefixlen == 0]
    if world:
        # QW-2 (H-2): 0.0.0.0/0 or ::/0 means "trust X-Forwarded-For from
        # anyone", which lets every client mint a fresh rate-limit bucket
        # per request. Refuse to boot in that state.
        message = (
            "TRUSTED_PROXY_CIDRS contains a world route "
            f"({', '.join(str(n) for n in world)}). Trusting X-Forwarded-For "
            "from every peer defeats rate limiting — narrow it to the actual "
            "proxy ranges (e.g. '127.0.0.1/32' or your load balancer CIDRs)."
        )
        if environment != "development":
            raise ValueError(message)
        logger.warning("%s Permitted only because ENVIRONMENT=development.", message)
    if not cidrs:
        if environment != "development":
            raise ValueError(
                "TRUSTED_PROXY_CIDRS parsed to zero valid networks in a "
                f"non-development environment (ENVIRONMENT={environment!r}). "
                "Set a valid comma-separated CIDR list (e.g. '127.0.0.1/32') so "
                "a spoofed X-Forwarded-For header cannot bypass per-IP rate "
                "limiting."
            )
        logger.warning(
            "TRUSTED_PROXY_CIDRS parsed to zero networks; permitted only "
            "because ENVIRONMENT=development."
        )
    return cidrs


def _client_identity(request: Request, trusted: Tuple[ipaddress.IPv4Network, ...]) -> str:
    """Resolve a stable per-client identity for the rate-limit key.

    Preference order:
      1. Authenticated tenant UUID (set by ``require_api_client``). This
         means an authenticated customer gets their own bucket independent
         of which proxy IP is forwarding.
      2. First entry in ``X-Forwarded-For`` *if* the immediate peer is in
         ``TRUSTED_PROXY_CIDRS``.
      3. The connecting socket peer.

    Returns ``"anonymous"`` if no identity can be resolved (extremely
    rare; e.g. Starlette test client with no client tuple).
    """

    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return f"tenant:{tenant_id}"

    peer_host = request.client.host if request.client else None
    if peer_host and trusted:
        try:
            peer_ip = ipaddress.ip_address(peer_host)
        except ValueError:
            peer_ip = None
        if peer_ip is not None and any(peer_ip in net for net in trusted):
            xff = request.headers.get("x-forwarded-for", "")
            forwarded = xff.split(",")[0].strip() if xff else ""
            if forwarded:
                return f"xff:{forwarded}"

    if peer_host:
        return f"ip:{peer_host}"
    return "anonymous"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client rate limiter backed by Redis (via slowapi).

    Disabled when ``BUDDI_RATE_LIMIT_DISABLED=1`` (CI / unit tests).
    Production deployments leave it on; the limits in
    :class:`RateLimitConfig` are tuned to the conservative per-tenant
    posture described in the strategic manual.
    """

    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self._config = config or RateLimitConfig()
        self._trusted = _trusted_proxy_cidrs()
        self._enabled = os.getenv("BUDDI_RATE_LIMIT_DISABLED", "").strip() not in {"1", "true", "yes"}
        # H-1: consecutive storage-error streak driving the expensive-path
        # fail-closed behaviour in _check(). Reset on any successful hit.
        self._consecutive_storage_errors = 0

        storage_uri = self._config.storage_uri or os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
        # slowapi's Limiter owns the connection pool and the moving-window
        # strategy. We never use its decorator API — we call into its
        # underlying ``limits`` strategy from dispatch() so we can keep
        # this codebase's bespoke 429 response shape and headers.
        self._rate_item = parse_rate_limit(
            f"{self._config.requests_per_window}/{int(self._config.window_seconds)} seconds"
        )
        self._slow = SlowAPILimiter(
            key_func=lambda _request: "unused",
            storage_uri=storage_uri,
            default_limits=[str(self._rate_item)],
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._enabled:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in self._config.exempt_path_prefixes):
            return await call_next(request)

        # CORS preflight requests are not user-initiated traffic in the
        # rate-limit sense — letting the browser preflight pass cleanly
        # avoids spurious 429s in normal operation.
        if request.method == "OPTIONS":
            return await call_next(request)

        key = _client_identity(request, self._trusted)
        allowed, retry_after = self._check(key, path)
        if not allowed:
            request_id = getattr(request.state, "request_id", None)
            logger.info(
                "Rate-limited request: key=%s path=%s retry_after=%.2fs request_id=%s",
                key,
                path,
                retry_after,
                request_id,
            )
            headers = {
                "Retry-After": str(max(1, int(round(retry_after)))),
                "X-RateLimit-Limit": str(self._config.requests_per_window),
                "X-RateLimit-Window-Seconds": str(int(self._config.window_seconds)),
            }
            if request_id:
                headers[REQUEST_ID_HEADER] = request_id
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Slow down and retry after the indicated interval.",
                    "retry_after_seconds": round(retry_after, 2),
                },
                headers=headers,
            )
        return await call_next(request)

    def _check(self, key: str, path: str = "") -> Tuple[bool, float]:
        """Consume one token for ``key``. Returns ``(allowed, retry_after)``.

        H-1: cheap paths fail open on storage errors (a Redis outage must
        not take the API offline), but after
        ``config.max_consecutive_storage_errors`` consecutive failures the
        LLM/cost-heavy prefixes in ``config.expensive_path_prefixes`` fail
        CLOSED — unbounded Anthropic spend is the worse outage. Either way
        we log loudly so the on-call dashboard can alarm on it.
        """

        strategy = self._slow.limiter
        try:
            allowed = strategy.hit(self._rate_item, key, cost=1)
        except Exception:
            self._consecutive_storage_errors += 1
            fail_closed = (
                self._consecutive_storage_errors >= self._config.max_consecutive_storage_errors
                and any(path.startswith(prefix) for prefix in self._config.expensive_path_prefixes)
            )
            if fail_closed:
                logger.exception(
                    "Rate-limit storage error #%d — failing CLOSED for expensive path=%s key=%s",
                    self._consecutive_storage_errors,
                    path,
                    key,
                )
                return False, float(self._config.window_seconds)
            logger.exception("Rate-limit storage error — failing open for key=%s", key)
            return True, 0.0
        self._consecutive_storage_errors = 0

        if allowed:
            return True, 0.0

        try:
            stats = strategy.get_window_stats(self._rate_item, key)
            retry_after = max(0.0, float(stats.reset_time) - time.time())
        except Exception:
            logger.exception("Rate-limit window-stats error for key=%s", key)
            retry_after = float(self._config.window_seconds)
        return False, retry_after

    # Test helpers ----------------------------------------------------------

    def reset(self) -> None:
        """Clear all counters. Only supported by storages that implement it."""

        try:
            self._slow.reset()
        except Exception:
            logger.warning("Rate-limit storage does not support reset()", exc_info=True)


__all__ = [
    "DEFAULT_REDIS_URL",
    "REQUEST_ID_HEADER",
    "RateLimitConfig",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
]

"""Starlette middleware for Buddi backend.

Provides two ASGI middlewares that ``backend/api.py`` wires in at app
construction:

  * ``RequestIDMiddleware`` — assigns a stable UUID to every incoming
    request, exposes it on ``request.state.request_id`` and as an
    ``X-Request-ID`` response header. Used by structured logging, audit
    persistence, and operator-UI error reporting.
  * ``RateLimitMiddleware`` — per-client-IP token bucket. The current
    implementation is **in-memory** which is correct for a single Cloud
    Run revision (min=1). The strategic manual (§4.2 Bottleneck #1)
    flags this as the first thing that will break at horizontal scale
    and prescribes a Redis-backed ``slowapi`` swap; that contract is
    captured below as ``# TODO(human): swap to Redis-backed slowapi``
    so the seam is obvious in code review.

CI / unit tests disable the limiter via ``BUDDI_RATE_LIMIT_DISABLED=1``
(see ``.github/workflows/main.yml``). Production deployments leave it
on with the defaults in :class:`RateLimitConfig`.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Awaitable, Callable, Dict, Optional, Tuple

from fastapi.responses import JSONResponse
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
# Rate limiter (in-memory token bucket)
# ---------------------------------------------------------------------------


@dataclass
class RateLimitConfig:
    """Tunable defaults for the rate limiter.

    The numbers are deliberately conservative — see
    ``Buddi_Strategic_Founders_Operating_Manual.pdf §4.2`` for why a real
    customer's nightly batch will saturate this at scale and what the
    Redis-backed replacement looks like.
    """

    #: Requests permitted in ``window_seconds`` per client identity.
    requests_per_window: int = 30
    window_seconds: float = 60.0

    #: Maximum number of unique buckets to track before we start LRU-evicting.
    #: 50k is plenty for a single revision and bounds the memory leak in the
    #: pathological case (one bucket per attacker IP).
    max_buckets: int = 50_000

    #: Paths that are exempt from rate limiting (health probes, signed-
    #: roots listing for ops, etc.).
    exempt_path_prefixes: Tuple[str, ...] = (
        "/health",
        "/internal/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    )


@dataclass
class _Bucket:
    """Single-IP token-bucket state."""

    tokens: float
    last_refill: float
    last_seen: float = field(default_factory=time.monotonic)


class _TokenBucketLimiter:
    """Pure-Python token bucket. Thread-safe via a single coarse lock.

    Refill semantics: at every check we top up ``tokens`` by the elapsed
    time times the configured refill rate, capped at the bucket size.
    Each accepted request decrements one token; if the bucket would go
    negative we reject with 429.
    """

    def __init__(self, config: RateLimitConfig):
        self._config = config
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = Lock()
        # Refill rate in tokens/second.
        self._rate = config.requests_per_window / max(config.window_seconds, 1e-6)

    def check(self, key: str) -> Tuple[bool, float]:
        """Try to consume one token. Returns ``(allowed, retry_after_seconds)``."""

        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(
                    tokens=self._config.requests_per_window - 1,
                    last_refill=now,
                    last_seen=now,
                )
                self._buckets[key] = bucket
                self._maybe_evict(now)
                return True, 0.0

            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(
                float(self._config.requests_per_window),
                bucket.tokens + elapsed * self._rate,
            )
            bucket.last_refill = now
            bucket.last_seen = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0

            deficit = 1.0 - bucket.tokens
            retry_after = deficit / max(self._rate, 1e-6)
            return False, retry_after

    def _maybe_evict(self, now: float) -> None:
        """Lazy LRU-ish eviction so a flood of unique IPs can't OOM us."""

        if len(self._buckets) <= self._config.max_buckets:
            return
        # Evict the 10% oldest buckets. Sorted scan is O(n log n) but
        # only triggers when we cross the cap, so amortised cost is fine.
        target_remaining = int(self._config.max_buckets * 0.9)
        ordered = sorted(self._buckets.items(), key=lambda kv: kv[1].last_seen)
        for key, _ in ordered[: max(0, len(ordered) - target_remaining)]:
            self._buckets.pop(key, None)

    # Test helpers ----------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def state_for(self, key: str) -> Optional[_Bucket]:  # pragma: no cover (debug)
        with self._lock:
            return self._buckets.get(key)


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
    """Per-client token-bucket rate limiter.

    Disabled when ``BUDDI_RATE_LIMIT_DISABLED=1`` (CI / unit tests).
    Production deployments leave it on; the limits in
    :class:`RateLimitConfig` are tuned to a conservative single-revision
    Cloud Run posture.

    # TODO(human): swap to Redis-backed slowapi.
    # This in-memory bucket only works on a single Cloud Run revision.
    # The moment we scale to N instances the effective per-client limit
    # becomes ``N × requests_per_window`` because each instance carries
    # its own bucket. See
    # ``Buddi_Strategic_Founders_Operating_Manual.pdf §4.2 Bottleneck #1``
    # and ``BUILD_PLAN.md`` for the Memorystore (managed Redis) plan.
    """

    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self._config = config or RateLimitConfig()
        self._limiter = _TokenBucketLimiter(self._config)
        self._trusted = _trusted_proxy_cidrs()
        self._enabled = os.getenv("BUDDI_RATE_LIMIT_DISABLED", "").strip() not in {"1", "true", "yes"}

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
        allowed, retry_after = self._limiter.check(key)
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

    # Test helpers ----------------------------------------------------------

    def reset(self) -> None:
        self._limiter.reset()


__all__ = [
    "REQUEST_ID_HEADER",
    "RateLimitConfig",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
]

"""Tests for the Redis-backed rate limiter in ``backend/middleware.py``.

These tests prove the property that motivated the rewrite (manual §4.2
Bottleneck #1): two middleware instances pointed at the same Redis
share a single bucket per client identity, so the effective limit at
horizontal scale equals the configured limit — not ``N × limit``.

Redis isn't required to run the suite. We monkey-patch
``redis.Redis.from_url`` so the ``limits`` package, which slowapi wraps,
gets a fakeredis client whenever it tries to open a connection from a
``redis://`` URI.
"""

from __future__ import annotations

import fakeredis
import pytest
import redis
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.middleware import (
    RateLimitConfig,
    RateLimitMiddleware,
)


@pytest.fixture(autouse=True)
def _force_limiter_enabled(monkeypatch):
    """Exercise the real limiter code path in this module.

    conftest.py disables the limiter suite-wide (``BUDDI_RATE_LIMIT_DISABLED=1``).
    We clear it *per test* — rather than at import time — so this module's apps
    build with the limiter ON without leaking the unset into the session-scoped
    ``client`` fixture. That client's middleware stack builds lazily during the
    run; an import-time ``os.environ.pop`` would leave it enabled and let request
    counts accumulate into spurious 429s in unrelated suites. ``monkeypatch``
    restores the previous value after each test.
    """
    monkeypatch.delenv("BUDDI_RATE_LIMIT_DISABLED", raising=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    """Route every ``redis.from_url`` call to a shared fakeredis server.

    All limiter instances created during a single test thus see the same
    counters, which is exactly what we need to assert the
    "shared-across-instances" property.
    """

    server = fakeredis.FakeServer()

    def _from_url(url, *args, **kwargs):
        return fakeredis.FakeStrictRedis(server=server, decode_responses=False)

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, url, **kw: _from_url(url, **kw)))
    monkeypatch.setattr(redis, "from_url", _from_url)
    return server


def _build_app(config: RateLimitConfig) -> Starlette:
    async def ok(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/echo", ok)])
    app.add_middleware(RateLimitMiddleware, config=config)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rate_limit_blocks_after_configured_requests(fake_redis):
    """The N+1th request inside the window must return 429 with our shape."""

    config = RateLimitConfig(
        requests_per_window=3,
        window_seconds=60.0,
        storage_uri="redis://fake:6379/0",
    )
    app = _build_app(config)
    client = TestClient(app)

    for _ in range(3):
        resp = client.get("/echo")
        assert resp.status_code == 200

    blocked = client.get("/echo")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["detail"].startswith("Rate limit exceeded")
    assert "retry_after_seconds" in body
    assert blocked.headers["Retry-After"]
    assert blocked.headers["X-RateLimit-Limit"] == "3"
    assert blocked.headers["X-RateLimit-Window-Seconds"] == "60"


def test_rate_limit_shared_across_middleware_instances(fake_redis):
    """Two app instances backed by the same Redis must share one bucket.

    This is the regression guard for the manual §4.2 bug: with the old
    in-memory bucket, ``N × requests_per_window`` was the effective
    limit because each Cloud Run revision had its own dict.
    """

    config = RateLimitConfig(
        requests_per_window=2,
        window_seconds=60.0,
        storage_uri="redis://fake:6379/0",
    )
    client_a = TestClient(_build_app(config))
    client_b = TestClient(_build_app(config))

    # One request from each app — both 200 because two are allowed.
    assert client_a.get("/echo").status_code == 200
    assert client_b.get("/echo").status_code == 200

    # The third request, no matter which app it hits, must be blocked.
    blocked = client_a.get("/echo")
    assert blocked.status_code == 429


def test_exempt_paths_skip_the_limiter(fake_redis):
    config = RateLimitConfig(
        requests_per_window=1,
        window_seconds=60.0,
        storage_uri="redis://fake:6379/0",
    )

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/health", health)])
    app.add_middleware(RateLimitMiddleware, config=config)
    client = TestClient(app)

    # /health is exempt — repeated hits never trip the limit.
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_disabled_env_flag_short_circuits_limiter(monkeypatch, fake_redis):
    monkeypatch.setenv("BUDDI_RATE_LIMIT_DISABLED", "1")
    config = RateLimitConfig(
        requests_per_window=1,
        window_seconds=60.0,
        storage_uri="redis://fake:6379/0",
    )
    client = TestClient(_build_app(config))

    for _ in range(5):
        assert client.get("/echo").status_code == 200


def test_authenticated_tenant_gets_isolated_bucket(fake_redis):
    """Two tenants must not share a bucket even from the same socket peer."""

    config = RateLimitConfig(
        requests_per_window=1,
        window_seconds=60.0,
        storage_uri="redis://fake:6379/0",
    )

    async def ok(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    class StampTenant:
        def __init__(self, app, tenant_id: str):
            self.app = app
            self.tenant_id = tenant_id

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                # Mirror what require_api_client does upstream.
                scope.setdefault("state", {})
            # Use a request-scope wrapper to set state.tenant_id before
            # RateLimitMiddleware reads it.
            async def _send(msg):
                await send(msg)
            request = Request(scope)
            request.state.tenant_id = self.tenant_id
            await self.app(scope, receive, _send)

    def _client_for(tenant: str) -> TestClient:
        app = Starlette(routes=[Route("/echo", ok)])
        app.add_middleware(RateLimitMiddleware, config=config)
        app.add_middleware(StampTenant, tenant_id=tenant)
        return TestClient(app)

    tenant_a = _client_for("tenant-aaa")
    tenant_b = _client_for("tenant-bbb")

    assert tenant_a.get("/echo").status_code == 200
    # Different tenant → fresh bucket, even though the socket peer is identical.
    assert tenant_b.get("/echo").status_code == 200

    # Same tenant tripping the limit blocks only that tenant.
    assert tenant_a.get("/echo").status_code == 429
    assert tenant_b.get("/echo").status_code == 429

"""
DEPRECATED — legacy `app.main` FastAPI entry point.

Buddi canonicalized on ``backend.api:app`` (port 8001) per Track 1 / Step 1
of the launch audit (ARCH-01, CFG-01, DO-01). This module is retained solely
to keep any lingering imports of ``app.main`` resolvable during the
decommissioning window; it MUST NOT be deployed.

Behavior:

* Importing this module emits a loud ``DeprecationWarning`` and an error-level
  log record so accidental use is visible in CI, staging, and production logs.
* Every HTTP route on the returned ``app`` instance returns HTTP 410 Gone
  with a JSON payload pointing at the canonical API. There are no live
  routers, no CORS middleware, no mock services — nothing to exploit.
* Running this module directly (``python -m app.main``) raises ``RuntimeError``.
"""
from __future__ import annotations

import logging
import warnings

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_CANONICAL = "backend.api:app on port 8001"
_DEPRECATION_MSG = (
    f"app.main is deprecated. The canonical Buddi API is {_CANONICAL}. "
    "Update your Dockerfile / docker-compose / launcher to reference it. "
    "See Track 1 / Step 1 of the launch audit (ARCH-01)."
)

logging.getLogger(__name__).error(_DEPRECATION_MSG)
warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

app = FastAPI(
    title="Buddi (DEPRECATED legacy API)",
    description=_DEPRECATION_MSG,
    version="0.0.0-deprecated",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def _gone(full_path: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "error": "gone",
            "message": _DEPRECATION_MSG,
            "canonical_api": _CANONICAL,
            "requested_method": request.method,
            "requested_path": f"/{full_path}",
        },
    )


if __name__ == "__main__":  # pragma: no cover
    raise RuntimeError(_DEPRECATION_MSG)

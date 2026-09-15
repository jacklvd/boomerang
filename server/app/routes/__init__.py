"""HTTP route modules, aggregated onto the one versioned router the app mounts.

Adding a route is two edits and neither of them is in ``app.main``: write a module in
this package that exposes a module-level ``router = APIRouter()`` with paths relative to
the version prefix (``@router.get("/me")``, not ``"/v1/me"``), then import it and
include it below.

The ``/v1`` prefix lives here, on the aggregator, rather than on each module's own
router. That way the version appears exactly once in the codebase, every route module
looks the same, and ``app.main`` includes this router once and never needs touching
again.
"""

from fastapi import APIRouter

from app.routes import dashboard, items, me

api_router = APIRouter(prefix="/v1")
api_router.include_router(me.router)
api_router.include_router(items.router)
api_router.include_router(dashboard.router)

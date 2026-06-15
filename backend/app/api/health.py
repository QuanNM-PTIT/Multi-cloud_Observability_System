from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Return a lightweight health response for load balancers and uptime checks."""
    return {"status": "ok", "service": "observability-backend"}

from fastapi import APIRouter

from app.services.model_provider import provider_catalog

router = APIRouter()


@router.get("/providers")
async def providers() -> dict[str, object]:
    """Return public provider defaults; never returns API keys."""
    return {"providers": provider_catalog()}

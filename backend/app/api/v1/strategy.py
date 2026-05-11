from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_strategies():
    """List all strategies."""
    return {"strategies": [], "count": 0}

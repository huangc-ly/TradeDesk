from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_portfolio():
    """Get current portfolio snapshot."""
    return {"positions": [], "total_value": 0}

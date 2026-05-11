from fastapi import APIRouter
from api.models import Feedback

router = APIRouter(prefix="/api", tags=["sendFeedback"])

@router.post("/sendFeedback")
async def sendFeedback(req: list[Feedback]) -> int:
    print(req)
    return 200
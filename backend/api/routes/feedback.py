import traceback
from fastapi import APIRouter, Request, HTTPException
from api.models import Feedback

router = APIRouter(prefix="/api", tags=["sendFeedback"])

def _get_feedback_logger(request: Request):
    return getattr(request.app.state, "feedback_logger", None)

@router.post("/sendFeedback")
async def sendFeedback(req: list[Feedback], request: Request) -> int:
    print(req)
    feedback_logger = _get_feedback_logger(request)
    if feedback_logger is None:
        print(f"[FEEDBACK_ROUTE] ⚠ Failed to load feedback logger")
        raise HTTPException(
            status_code=500,
            detail="Failed to load feedback logger",
        )
    try:
        await feedback_logger.log_feedback(req)
        return 200
    except Exception as e:
        print(f"[FEEDBACK_ROUTE] ⚠ Failed to log feedback : {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to log feedback",
        )
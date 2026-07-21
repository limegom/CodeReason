from app.api.routes.assignments import router as assignments_router
from app.api.routes.consistency import router as consistency_router
from app.api.routes.demo import router as demo_router
from app.api.routes.submissions import router as submissions_router
from app.api.routes.reviewer import router as reviewer_router
from app.api.routes.operations import router as operations_router

__all__ = [
    "assignments_router",
    "consistency_router",
    "demo_router",
    "operations_router",
    "reviewer_router",
    "submissions_router",
]

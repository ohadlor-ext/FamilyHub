from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from routers.auth import get_current_user_dep
from routers.family import _compute_age
from models.user import User, UserRole, ChildProfile
from services.claude_ai import get_homework_help, get_smart_schedule_suggestion

router = APIRouter(prefix="/ai", tags=["ai"])


class HomeworkMessage(BaseModel):
    question: str
    conversation_history: Optional[List[dict]] = None


class HomeworkResponse(BaseModel):
    response: str
    updated_history: List[dict]
    tokens_used: int


@router.post("/homework/{child_user_id}", response_model=HomeworkResponse)
def homework_help(
    child_user_id: int,
    message: HomeworkMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    if current_user.id != child_user_id and current_user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="אין הרשאה")

    child_user = db.query(User).filter(User.id == child_user_id).first()
    if not child_user:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    profile = db.query(ChildProfile).filter(ChildProfile.user_id == child_user_id).first()

    result = get_homework_help(
        question=message.question,
        child_name=child_user.name.split()[0],
        child_age=_compute_age(profile.birth_date, profile.age) if profile else 10,
        child_grade=profile.grade if profile else "ה'",
        subjects=profile.subjects if profile else [],
        conversation_history=message.conversation_history,
        homework_level=profile.homework_level if profile else "standard",
        interests=profile.interests if profile else [],
        school=profile.school if profile else None,
    )
    return HomeworkResponse(**result)


@router.get("/schedule-tip")
def schedule_tip(
    current_user: User = Depends(get_current_user_dep),
):
    from services.google_calendar import get_upcoming_events
    events = get_upcoming_events(
        access_token=current_user.google_access_token,
        refresh_token=current_user.google_refresh_token,
        days_ahead=7,
        max_results=5,
    )
    tip = get_smart_schedule_suggestion(
        family_events=events,
        tasks=[],
        user_name=current_user.name.split()[0],
    )
    return {"tip": tip}

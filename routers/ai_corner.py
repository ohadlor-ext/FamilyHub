"""
פינת AI לילדים — יצירת תוכן (סיפור/סקרנות/חידה-בדיחה/יצירה), מועדפים, ויומן צפייה
להורה. כל יצירה נשמרת ב-AICornerLog (ראו דוקסטרינג מלא ב-models/ai_corner.py) —
זה גם המקור למועדפים וגם ל"יומן צפייה" שהורה יכול לראות בהגדרות (פיקוח/בטיחות).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole, ChildProfile
from models.ai_corner import AICornerLog, AICornerFavorite
from routers.auth import get_current_user_dep
from routers.family import _compute_age
from services.claude_ai import get_ai_corner_content

router = APIRouter(prefix="/ai-corner", tags=["ai-corner"])

CONTENT_TYPES = {"story", "curiosity", "riddle_joke", "creative"}


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


def _require_self_or_parent(user: User, child_id: int):
    if user.role == UserRole.CHILD and user.id != child_id:
        raise HTTPException(status_code=403, detail="אין הרשאה")


class GenerateRequest(BaseModel):
    content_type: str
    topic: Optional[str] = None


class FavoriteCreate(BaseModel):
    log_id: int


@router.post("/generate/{child_user_id}")
def generate_content(
    child_user_id: int,
    data: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_self_or_parent(current_user, child_user_id)

    if data.content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="סוג תוכן לא מוכר")
    if data.content_type == "curiosity" and not (data.topic and data.topic.strip()):
        raise HTTPException(status_code=400, detail="יש לכתוב שאלה")

    child_user = db.query(User).filter(User.id == child_user_id, User.role == UserRole.CHILD).first()
    if not child_user:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    profile = db.query(ChildProfile).filter(ChildProfile.user_id == child_user_id).first()

    result = get_ai_corner_content(
        content_type=data.content_type,
        child_name=child_user.name.split()[0],
        child_age=_compute_age(profile.birth_date, profile.age) if profile else 8,
        interests=profile.interests if profile else [],
        topic=data.topic,
    )

    log = AICornerLog(
        child_id=child_user_id,
        content_type=data.content_type,
        topic=data.topic,
        title=result.get("title"),
        content=result.get("content") or "",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "content_type": log.content_type,
        "title": log.title,
        "content": log.content,
        "created_at": log.created_at,
    }


@router.get("/favorites")
def list_favorites(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_self_or_parent(current_user, child_id)
    favorites = (
        db.query(AICornerFavorite)
        .filter(AICornerFavorite.child_id == child_id)
        .order_by(AICornerFavorite.created_at.desc())
        .all()
    )
    return {
        "favorites": [
            {
                "id": f.id,
                "content_type": f.content_type,
                "title": f.title,
                "content": f.content,
                "created_at": f.created_at,
            }
            for f in favorites
        ]
    }


@router.post("/favorites")
def add_favorite(
    data: FavoriteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    log = db.query(AICornerLog).filter(AICornerLog.id == data.log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="התוכן לא נמצא")
    _require_self_or_parent(current_user, log.child_id)

    favorite = AICornerFavorite(
        child_id=log.child_id,
        log_id=log.id,
        content_type=log.content_type,
        title=log.title,
        content=log.content,
    )
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return {"message": "נשמר למועדפים", "id": favorite.id}


@router.delete("/favorites/{favorite_id}")
def delete_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    favorite = db.query(AICornerFavorite).filter(AICornerFavorite.id == favorite_id).first()
    if not favorite:
        raise HTTPException(status_code=404, detail="המועדף לא נמצא")
    _require_self_or_parent(current_user, favorite.child_id)

    db.delete(favorite)
    db.commit()
    return {"message": "המועדף הוסר"}


@router.get("/log")
def get_log(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """יומן צפייה להורה — כל מה שכל ילד שאל/קיבל בפינת ה-AI."""
    _require_parent(current_user)
    entries = (
        db.query(AICornerLog)
        .filter(AICornerLog.child_id == child_id)
        .order_by(AICornerLog.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "entries": [
            {
                "id": e.id,
                "content_type": e.content_type,
                "topic": e.topic,
                "title": e.title,
                "content": e.content,
                "created_at": e.created_at,
            }
            for e in entries
        ]
    }

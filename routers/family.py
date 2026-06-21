"""
Family Members — ניהול פרופילי ילדים (בלי חיבור Google)
הורה יוצר פרופיל לכל ילד מהדשבורד, כדי שתכונות כמו עזרה בשיעורי בית
ידעו עם איזה user_id אמיתי לעבוד — בלי שהילד יצטרך חשבון Google משלו.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import ChildProfile, User, UserRole
from routers.auth import get_current_user_dep

router = APIRouter(prefix="/family", tags=["family"])


class ChildCreate(BaseModel):
    name: str
    age: Optional[int] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    subjects: List[str] = []
    avatar_emoji: str = "🧒"
    color_theme: str = "#6C63FF"


class ChildUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    subjects: Optional[List[str]] = None
    avatar_emoji: Optional[str] = None
    color_theme: Optional[str] = None


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


@router.get("/members")
def list_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """כל בני המשפחה הפעילים — להורים ולילדים, לבחירת משתמש בממשק (לדוגמה: עזרה בשיעורי בית)"""
    users = db.query(User).filter(User.is_active == True).all()
    members = []
    for u in users:
        member = {
            "id": u.id,
            "name": u.name,
            "role": u.role,
            "picture": u.picture,
        }
        if u.child_profile:
            member.update({
                "age": u.child_profile.age,
                "grade": u.child_profile.grade,
                "school": u.child_profile.school,
                "avatar_emoji": u.child_profile.avatar_emoji,
                "color_theme": u.child_profile.color_theme,
            })
        members.append(member)
    return {"members": members}


@router.post("/children")
def create_child(
    child: ChildCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הורה יוצר פרופיל לילד — בלי חיבור Google, לשימוש בקיוסק המשותף"""
    _require_parent(current_user)

    synthetic_id = f"child-{uuid.uuid4().hex[:12]}"
    user = User(
        google_id=synthetic_id,
        email=f"{synthetic_id}@family.local",
        name=child.name,
        role=UserRole.CHILD,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = ChildProfile(
        user_id=user.id,
        age=child.age,
        grade=child.grade,
        school=child.school,
        subjects=child.subjects,
        avatar_emoji=child.avatar_emoji,
        color_theme=child.color_theme,
    )
    db.add(profile)
    db.commit()

    return {"message": "פרופיל ילד נוצר", "id": user.id}


@router.patch("/children/{child_id}")
def update_child(
    child_id: int,
    update: ChildUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)

    user = db.query(User).filter(
        User.id == child_id, User.role == UserRole.CHILD
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    if update.name is not None:
        user.name = update.name

    profile = db.query(ChildProfile).filter(ChildProfile.user_id == child_id).first()
    if profile:
        for field in ("age", "grade", "school", "subjects", "avatar_emoji", "color_theme"):
            value = getattr(update, field)
            if value is not None:
                setattr(profile, field, value)

    db.commit()
    return {"message": "פרופיל עודכן"}


@router.delete("/children/{child_id}")
def delete_child(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """מחיקה רכה (is_active=False) — לא מוחק היסטוריית משימות/שיעורי בית"""
    _require_parent(current_user)

    user = db.query(User).filter(
        User.id == child_id, User.role == UserRole.CHILD
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    user.is_active = False
    db.commit()
    return {"message": "פרופיל הוסר"}

"""
Family Members — ניהול פרופילי ילדים (בלי חיבור Google)
הורה יוצר פרופיל לכל ילד מהדשבורד, כדי שתכונות כמו עזרה בשיעורי בית
ידעו עם איזה user_id אמיתי לעבוד — בלי שהילד יצטרך חשבון Google משלו.
"""
import uuid
from datetime import date
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
    age: Optional[int] = None  # גיבוי ידני — אם יש birth_date, הוא קודם
    birth_date: Optional[date] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    subjects: List[str] = []
    homework_level: str = "standard"
    interests: List[str] = []
    notes: Optional[str] = None
    avatar_emoji: str = "🧒"
    color_theme: str = "#6C63FF"
    email: Optional[str] = None  # Gmail אמיתי של הילד — אם יש, ישמש לקישור אוטומטי בכניסה ראשונה עם Google


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    birth_date: Optional[date] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    subjects: Optional[List[str]] = None
    homework_level: Optional[str] = None
    interests: Optional[List[str]] = None
    notes: Optional[str] = None
    avatar_emoji: Optional[str] = None
    color_theme: Optional[str] = None
    email: Optional[str] = None


def _is_synthetic_email(email: str) -> bool:
    """אימייל פיקטיבי שנוצר לילד בלי Gmail אמיתי (ראה create_child) — לא להציג להורה"""
    return email.endswith("@family.local")


def _compute_age(birth_date: Optional[date], fallback_age: Optional[int]) -> Optional[int]:
    """גיל מחושב מתאריך לידה (מתעדכן מעצמו) — עם גיבוי לשדה age הישן לפרופילים שנוצרו לפניו"""
    if birth_date:
        today = date.today()
        had_birthday_this_year = (today.month, today.day) >= (birth_date.month, birth_date.day)
        return today.year - birth_date.year - (0 if had_birthday_this_year else 1)
    return fallback_age


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
        # לילדים: avatar_emoji/color_theme יושבים ב-ChildProfile.
        # להורים: אין להם ChildProfile, אז שומרים את אותם שדות בתוך User.settings (JSON קיים) —
        # כך שאפשר לערוך גם הורים בלי מיגרציה של עמודות חדשות בטבלת users.
        user_settings = u.settings or {}
        if u.child_profile:
            avatar_emoji = u.child_profile.avatar_emoji or "🧒"
            color_theme = u.child_profile.color_theme or "#6C63FF"
        else:
            avatar_emoji = user_settings.get("avatar_emoji") or "🧑"
            color_theme = user_settings.get("color_theme") or "#6C63FF"

        member = {
            "id": u.id,
            "name": u.name,
            "role": u.role,
            "picture": u.picture,
            "avatar_emoji": avatar_emoji,
            "color_theme": color_theme,
            # להורים האימייל הוא תמיד אמיתי (זה איך התחברו). לילדים — רק אם הוזן Gmail אמיתי,
            # לא את הכתובת הפיקטיבית שנוצרת אוטומטית בקיוסק.
            "email": u.email if (u.role != UserRole.CHILD or not _is_synthetic_email(u.email)) else None,
        }
        if u.child_profile:
            member.update({
                "age": _compute_age(u.child_profile.birth_date, u.child_profile.age),
                "birth_date": u.child_profile.birth_date.isoformat() if u.child_profile.birth_date else None,
                "grade": u.child_profile.grade,
                "school": u.child_profile.school,
                "subjects": u.child_profile.subjects or [],
                "homework_level": u.child_profile.homework_level,
                "interests": u.child_profile.interests or [],
                "notes": u.child_profile.notes,
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
        # אם ההורה הזין Gmail אמיתי של הילד — נשמור אותו כדי שכניסה עם Google תשייך
        # אוטומטית את החשבון לפרופיל הזה (ראה routers/auth.py google_callback).
        # אחרת, כתובת פיקטיבית — הילד ימשיך להשתמש בקיוסק המשותף בלי Google.
        email=child.email or f"{synthetic_id}@family.local",
        name=child.name,
        role=UserRole.CHILD,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = ChildProfile(
        user_id=user.id,
        age=child.age,
        birth_date=child.birth_date,
        grade=child.grade,
        school=child.school,
        subjects=child.subjects,
        homework_level=child.homework_level,
        interests=child.interests,
        notes=child.notes,
        avatar_emoji=child.avatar_emoji,
        color_theme=child.color_theme,
    )
    db.add(profile)
    db.commit()

    return {"message": "פרופיל ילד נוצר", "id": user.id}


@router.patch("/members/{member_id}")
def update_member(
    member_id: int,
    update: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """עדכון פרופיל של כל בן משפחה — הורה או ילד (הורים בלבד יכולים לערוך)"""
    _require_parent(current_user)

    user = db.query(User).filter(
        User.id == member_id, User.is_active == True
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="בן משפחה לא נמצא")

    if update.name is not None:
        user.name = update.name
    if update.email is not None and update.email.strip():
        user.email = update.email.strip()

    if user.role == UserRole.CHILD:
        profile = db.query(ChildProfile).filter(ChildProfile.user_id == member_id).first()
        if profile:
            for field in (
                "age", "birth_date", "grade", "school", "subjects",
                "homework_level", "interests", "notes", "avatar_emoji", "color_theme",
            ):
                value = getattr(update, field)
                if value is not None:
                    setattr(profile, field, value)
    else:
        # הורה — אין ChildProfile, שומרים emoji/color בתוך User.settings
        current_settings = dict(user.settings or {})
        if update.avatar_emoji is not None:
            current_settings["avatar_emoji"] = update.avatar_emoji
        if update.color_theme is not None:
            current_settings["color_theme"] = update.color_theme
        user.settings = current_settings

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

"""
לוח שגרה בוקר/ערב — צ'ק-ליסט פר ילד, מוצג בקיוסק עם כפתורים גדולים.
ההורה מגדיר את פריטי השגרה (במסך הגדרות), והילד מסמן "בוצע" בעצמו —
בלי הרשאת הורה, בדיוק כמו אצל משימות (routers/tasks.py).
"""
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.routine import RoutineItem, RoutineCompletion, RoutineType
from routers.auth import get_current_user_dep

router = APIRouter(prefix="/routines", tags=["routines"])

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# תבנית ברירת מחדל — כדי שלא צריך להתחיל מאפס בהגדרות (כפתור "טען רשימת ברירת מחדל")
DEFAULT_MORNING = [
    ("🛏️", "לסדר את המיטה"),
    ("🪥", "לצחצח שיניים"),
    ("👕", "להתלבש"),
    ("🎒", "לארוז תיק"),
]
DEFAULT_EVENING = [
    ("🛁", "מקלחת/אמבטיה"),
    ("🪥", "לצחצח שיניים"),
    ("🧸", "להכין פיג'מה"),
    ("🎒", "להכין תיק למחר"),
]


class RoutineItemCreate(BaseModel):
    child_id: int
    routine_type: RoutineType
    title: str
    emoji: str = "✅"
    sort_order: int = 0


class RoutineItemUpdate(BaseModel):
    routine_type: Optional[RoutineType] = None
    title: Optional[str] = None
    emoji: Optional[str] = None
    sort_order: Optional[int] = None


def _today() -> date_cls:
    """'היום' לפי שעון ישראל — כך שהאיפוס היומי קורה בחצות ישראל, לא UTC"""
    return datetime.now(ISRAEL_TZ).date()


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


def _serialize_item(item: RoutineItem, completed_today: bool) -> dict:
    return {
        "id": item.id,
        "routine_type": item.routine_type,
        "title": item.title,
        "emoji": item.emoji,
        "sort_order": item.sort_order,
        "completed": completed_today,
    }


@router.get("/today")
def get_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """שגרת היום לכל הילדים שיש להם פריטי שגרה מוגדרים — למסך הקיוסק"""
    today = _today()
    children = (
        db.query(User)
        .filter(User.role == UserRole.CHILD, User.is_active == True)
        .all()
    )

    result = []
    for child in children:
        items = (
            db.query(RoutineItem)
            .filter(RoutineItem.child_id == child.id)
            .order_by(RoutineItem.routine_type, RoutineItem.sort_order)
            .all()
        )
        if not items:
            continue  # ילד בלי תבנית שגרה מוגדרת — לא מוצג בכלל בקיוסק

        item_ids = [i.id for i in items]
        completed_ids = {
            c.routine_item_id
            for c in db.query(RoutineCompletion).filter(
                RoutineCompletion.routine_item_id.in_(item_ids),
                RoutineCompletion.date == today,
            )
        }

        profile = child.child_profile
        morning = [
            _serialize_item(i, i.id in completed_ids)
            for i in items if i.routine_type == RoutineType.MORNING
        ]
        evening = [
            _serialize_item(i, i.id in completed_ids)
            for i in items if i.routine_type == RoutineType.EVENING
        ]

        result.append({
            "child_id": child.id,
            "name": child.name,
            "avatar_emoji": (profile.avatar_emoji if profile else None) or "🧒",
            "color_theme": (profile.color_theme if profile else None) or "#6C63FF",
            "morning": morning,
            "evening": evening,
        })

    return {"date": today.isoformat(), "children": result}


@router.get("/items")
def list_items(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """תבנית השגרה המלאה של ילד אחד — למסך ההגדרות (לא תלוי בהשלמות יומיות)"""
    items = (
        db.query(RoutineItem)
        .filter(RoutineItem.child_id == child_id)
        .order_by(RoutineItem.routine_type, RoutineItem.sort_order)
        .all()
    )
    return {
        "items": [
            {
                "id": i.id,
                "routine_type": i.routine_type,
                "title": i.title,
                "emoji": i.emoji,
                "sort_order": i.sort_order,
            }
            for i in items
        ]
    }


@router.post("/items")
def create_item(
    item_data: RoutineItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הורה מוסיף פריט בודד לתבנית השגרה של ילד"""
    _require_parent(current_user)
    child = db.query(User).filter(
        User.id == item_data.child_id, User.role == UserRole.CHILD
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    item = RoutineItem(**item_data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "פריט שגרה נוסף", "id": item.id}


@router.post("/items/seed-defaults")
def seed_defaults(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """ממלא תבנית בסיסית (4 בוקר + 4 ערב) — רק אם לילד הזה אין עדיין שום פריט,
    כדי שכפתור 'טען רשימת ברירת מחדל' לא ידרוס פריטים שכבר הוגדרו ידנית"""
    _require_parent(current_user)
    child = db.query(User).filter(
        User.id == child_id, User.role == UserRole.CHILD
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    existing = db.query(RoutineItem).filter(RoutineItem.child_id == child_id).count()
    if existing:
        raise HTTPException(
            status_code=400, detail="לילד הזה כבר יש פריטי שגרה — אפשר להוסיף/לערוך ידנית"
        )

    created = 0
    for order, (emoji, title) in enumerate(DEFAULT_MORNING):
        db.add(RoutineItem(
            child_id=child_id, routine_type=RoutineType.MORNING,
            title=title, emoji=emoji, sort_order=order,
        ))
        created += 1
    for order, (emoji, title) in enumerate(DEFAULT_EVENING):
        db.add(RoutineItem(
            child_id=child_id, routine_type=RoutineType.EVENING,
            title=title, emoji=emoji, sort_order=order,
        ))
        created += 1
    db.commit()
    return {"message": f"נוספו {created} פריטי שגרה"}


@router.patch("/items/{item_id}")
def update_item(
    item_id: int,
    update: RoutineItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    item = db.query(RoutineItem).filter(RoutineItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט שגרה לא נמצא")

    for field, value in update.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    return {"message": "פריט שגרה עודכן"}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    item = db.query(RoutineItem).filter(RoutineItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט שגרה לא נמצא")
    db.delete(item)  # cascade="all, delete-orphan" מוחק גם את היסטוריית ההשלמות שלו
    db.commit()
    return {"message": "פריט שגרה נמחק"}


@router.post("/items/{item_id}/toggle")
def toggle_completion(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הילד (או הורה) מסמן/מבטל פריט שגרה להיום — toggle ולא set, כך שלחיצה כפולה בטעות מתקנת את עצמה"""
    item = db.query(RoutineItem).filter(RoutineItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט שגרה לא נמצא")

    if current_user.role == UserRole.CHILD and item.child_id != current_user.id:
        raise HTTPException(status_code=403, detail="אין הרשאה")

    today = _today()
    existing = db.query(RoutineCompletion).filter(
        RoutineCompletion.routine_item_id == item_id,
        RoutineCompletion.date == today,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"completed": False}

    db.add(RoutineCompletion(routine_item_id=item_id, date=today))
    db.commit()
    return {"completed": True}

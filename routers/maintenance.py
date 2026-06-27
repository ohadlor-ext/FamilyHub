"""
תחזוקת הבית — מעקב אחרי מכשירים/רכב לטיפול תקופתי, וגם מסמכים/ביטוחים עם תוקף שצריך
לזכור לחדש. ראו models/maintenance.py להסבר המלא על המודל המאוחד.
ניהול (יצירה/עריכה/מחיקה/סימון 'בוצע') — הורים בלבד, כמו בתשלומים.
תזכורת בפועל (טלגרם + קיוסק) — services/notifications.py:send_maintenance_reminders, קרון ב-main.py.
"""
import base64
import calendar
import io
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from PIL import Image

from database import get_db
from models.user import User, UserRole
from models.maintenance import MaintenanceItem, MaintenanceLog
from routers.auth import get_current_user_dep
from services.claude_ai import identify_maintenance_item_from_photo

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
MAX_IMAGE_DIMENSION = 1568  # אותו קבוע כמו routers/inventory.py — המלצת Anthropic


class MaintenanceCreate(BaseModel):
    name: str
    category: str = "אחר"
    next_due_date: date_cls
    recurrence_interval_months: Optional[int] = Field(default=None, ge=1, le=120)
    remind_days_before: int = Field(default=14, ge=0, le=180)
    provider_name: Optional[str] = None
    provider_phone: Optional[str] = None
    notes: Optional[str] = None


class MaintenanceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    next_due_date: Optional[date_cls] = None
    recurrence_interval_months: Optional[int] = Field(default=None, ge=1, le=120)
    remind_days_before: Optional[int] = Field(default=None, ge=0, le=180)
    provider_name: Optional[str] = None
    provider_phone: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class PhotoIdentifyResponse(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    next_due_date: Optional[str] = None
    provider_name: Optional[str] = None
    confidence: Optional[str] = None


def _today() -> date_cls:
    """'היום' לפי שעון ישראל — כך שתאריכי יעד מחושבים נכון גם סמוך לחצות"""
    return datetime.now(ISRAEL_TZ).date()


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


def _advance_due_date(d: date_cls, months: int) -> date_cls:
    """מקדם תאריך יעד ב-N חודשים — בלי תלות בספריות חיצוניות. אם היום המקורי לא קיים
    בחודש היעד (למשל 31 בחודש קצר), נתפס היום האחרון הקיים — מתנהג כמו 'סוף חודש'
    באופן טבעי (אותו עיקרון כמו routers/payments.py:_advance_due_date, אבל למרווח
    חודשים גמיש ולא enum קבוע של שבועי/חודשי/שנתי)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date_cls(year, month, day)


def _serialize(item: MaintenanceItem, today: date_cls) -> dict:
    days_until = (item.next_due_date - today).days
    if days_until < 0:
        status = "overdue"
    elif days_until <= item.remind_days_before:
        status = "due_soon"
    else:
        status = "ok"
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "next_due_date": item.next_due_date.isoformat(),
        "recurrence_interval_months": item.recurrence_interval_months,
        "remind_days_before": item.remind_days_before,
        "provider_name": item.provider_name,
        "provider_phone": item.provider_phone,
        "notes": item.notes,
        "is_active": item.is_active,
        "days_until_due": days_until,
        "status": status,
    }


def _process_image_upload(file: UploadFile) -> tuple:
    """קורא קובץ תמונה שהועלה, מקטין אם צריך, ומחזיר (base64, media_type).
    אותו עיקרון כמו routers/inventory.py — לא שומר את התמונה, רק מעבד לזיהוי חד-פעמי."""
    raw = file.file.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if max(img.size) > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = buf.getvalue()
        media_type = "image/jpeg"
    except Exception:
        data = raw
        media_type = file.content_type or "image/jpeg"
    return base64.b64encode(data).decode("utf-8"), media_type


@router.get("")
def list_maintenance_items(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """כל פריטי תחזוקת הבית (מכשירים/רכב/ביטוחים/מסמכים), ממוינים מהקרוב ביותר
    לתאריך יעד — להגדרות וגם לכרטיס בקיוסק"""
    query = db.query(MaintenanceItem)
    if not include_inactive:
        query = query.filter(MaintenanceItem.is_active == True)
    items = query.order_by(MaintenanceItem.next_due_date.asc()).all()

    today = _today()
    return {"items": [_serialize(i, today) for i in items]}


@router.post("")
def create_maintenance_item(
    data: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הורה מוסיף פריט תחזוקה/מסמך חדש (חזרתי או חד-פעמי)"""
    _require_parent(current_user)
    item = MaintenanceItem(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "פריט תחזוקה נוסף", "id": item.id}


@router.patch("/{item_id}")
def update_maintenance_item(
    item_id: int,
    update: MaintenanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    item = db.query(MaintenanceItem).filter(MaintenanceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט תחזוקה לא נמצא")

    for field, value in update.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    return {"message": "פריט תחזוקה עודכן"}


@router.delete("/{item_id}")
def delete_maintenance_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    item = db.query(MaintenanceItem).filter(MaintenanceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט תחזוקה לא נמצא")
    db.delete(item)  # cascade="all, delete-orphan" מוחק גם את ההיסטוריה שלו
    db.commit()
    return {"message": "פריט תחזוקה נמחק"}


@router.post("/{item_id}/mark-done")
def mark_done(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """מסמן שהמחזור הנוכחי בוצע/נסגר ורושם בהיסטוריה.
    חזרתי (recurrence_interval_months מוגדר): מתקדם אוטומטית ב-N חודשים.
    חד-פעמי (None): אין מחזור הבא — מסומן is_active=False ויוצא מהרשימה הפעילה,
    אבל ההיסטוריה שלו (MaintenanceLog) נשארת זמינה ב-GET /maintenance/{id}/history."""
    _require_parent(current_user)
    item = db.query(MaintenanceItem).filter(MaintenanceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט תחזוקה לא נמצא")

    done_period = item.next_due_date
    db.add(MaintenanceLog(maintenance_item_id=item.id, period_due_date=done_period))

    if item.recurrence_interval_months:
        item.next_due_date = _advance_due_date(done_period, item.recurrence_interval_months)
    else:
        item.is_active = False
    db.commit()

    return {
        "message": "סומן כבוצע",
        "done_period": done_period.isoformat(),
        "next_due_date": item.next_due_date.isoformat(),
        "is_active": item.is_active,
    }


@router.get("/{item_id}/history")
def maintenance_history(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    item = db.query(MaintenanceItem).filter(MaintenanceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט תחזוקה לא נמצא")

    logs = (
        db.query(MaintenanceLog)
        .filter(MaintenanceLog.maintenance_item_id == item_id)
        .order_by(MaintenanceLog.done_at.desc())
        .all()
    )
    return {
        "history": [
            {
                "id": log.id,
                "period_due_date": log.period_due_date.isoformat(),
                "done_at": log.done_at.isoformat() if log.done_at else None,
            }
            for log in logs
        ]
    }


@router.post("/identify-photo", response_model=PhotoIdentifyResponse)
def identify_photo(
    file: UploadFile = File(...),
    _=Depends(get_current_user_dep),
):
    """מזהה פריט תחזוקה/מסמך מתוך תמונה (Claude vision) — תווית מכשיר, מדבקת דגם,
    תעודת אחריות, פוליסת ביטוח. לא שומר את התמונה עצמה ולא כותב כלום ל-DB — מחזיר
    הצעה שהמשתמש מאשר/משלים בפרונט לפני שמירה (אותו עיקרון כמו /inventory/identify-photo)."""
    image_b64, media_type = _process_image_upload(file)
    result = identify_maintenance_item_from_photo(image_b64, media_type)
    return PhotoIdentifyResponse(**result)

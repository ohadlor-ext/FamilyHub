"""
תזכורות תשלום — תשלומים שצריך לשלם כדי שלא ייווצר חוב או אי-נעימות (ארנונה, ביטוחים,
מנויים — חזרתיים; אבל גם קנס או חוב חד-פעמי — recurrence=once).
ניהול (יצירה/עריכה/מחיקה/סימון 'שולם') — הורים בלבד, כי זה תחום פיננסי.
תזכורת בפועל (טלגרם + קיוסק) — services/notifications.py:send_payment_reminders, קרון ב-main.py.
"""
import calendar
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.payment import RecurringPayment, PaymentLog, PaymentRecurrence
from routers.auth import get_current_user_dep

router = APIRouter(prefix="/payments", tags=["payments"])

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


class PaymentCreate(BaseModel):
    title: str
    amount: Optional[float] = None
    recurrence: PaymentRecurrence
    next_due_date: date_cls
    remind_days_before: int = Field(default=3, ge=0, le=60)
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None
    recurrence: Optional[PaymentRecurrence] = None
    next_due_date: Optional[date_cls] = None
    remind_days_before: Optional[int] = Field(default=None, ge=0, le=60)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class MarkPaid(BaseModel):
    amount_paid: Optional[float] = None


def _today() -> date_cls:
    """'היום' לפי שעון ישראל — כך שתאריכי יעד מחושבים נכון גם סמוך לחצות"""
    return datetime.now(ISRAEL_TZ).date()


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


def _advance_due_date(d: date_cls, recurrence: PaymentRecurrence) -> date_cls:
    """מקדם תאריך יעד למחזור הבא, לפי סוג החזרתיות — בלי תלות בספריות חיצוניות.
    לחודשי/שנתי: אם היום המקורי לא קיים בחודש/שנה היעד (למשל 31 בפברואר), נתפס היום
    האחרון הקיים באותו חודש — מתנהג כמו 'סוף חודש' באופן טבעי."""
    if recurrence == PaymentRecurrence.WEEKLY:
        from datetime import timedelta
        return d + timedelta(weeks=1)

    if recurrence == PaymentRecurrence.MONTHLY:
        month = d.month + 1
        year = d.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date_cls(year, month, day)

    if recurrence == PaymentRecurrence.YEARLY:
        year = d.year + 1
        day = min(d.day, calendar.monthrange(year, d.month)[1])
        return date_cls(year, d.month, day)

    raise ValueError(f"סוג חזרתיות לא מוכר: {recurrence}")


def _serialize(p: RecurringPayment, today: date_cls) -> dict:
    days_until = (p.next_due_date - today).days
    if days_until < 0:
        status = "overdue"
    elif days_until <= p.remind_days_before:
        status = "due_soon"
    else:
        status = "ok"
    return {
        "id": p.id,
        "title": p.title,
        "amount": p.amount,
        "recurrence": p.recurrence,
        "next_due_date": p.next_due_date.isoformat(),
        "remind_days_before": p.remind_days_before,
        "notes": p.notes,
        "is_active": p.is_active,
        "days_until_due": days_until,
        "status": status,
    }


@router.get("")
def list_payments(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """כל תזכורות התשלום (חזרתיות וחד-פעמיות), ממוינות מהקרוב ביותר לתאריך יעד — להגדרות וגם לכרטיס בקיוסק"""
    query = db.query(RecurringPayment)
    if not include_inactive:
        query = query.filter(RecurringPayment.is_active == True)
    payments = query.order_by(RecurringPayment.next_due_date.asc()).all()

    today = _today()
    return {"payments": [_serialize(p, today) for p in payments]}


@router.post("")
def create_payment(
    payment_data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הורה מוסיף תזכורת תשלום חדשה (חזרתית או חד-פעמית)"""
    _require_parent(current_user)
    payment = RecurringPayment(**payment_data.model_dump())
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"message": "תזכורת תשלום נוספה", "id": payment.id}


@router.patch("/{payment_id}")
def update_payment(
    payment_id: int,
    update: PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    payment = db.query(RecurringPayment).filter(RecurringPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="תזכורת תשלום לא נמצאה")

    for field, value in update.model_dump(exclude_none=True).items():
        setattr(payment, field, value)
    db.commit()
    return {"message": "תזכורת תשלום עודכנה"}


@router.delete("/{payment_id}")
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    payment = db.query(RecurringPayment).filter(RecurringPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="תזכורת תשלום לא נמצאה")
    db.delete(payment)  # cascade="all, delete-orphan" מוחק גם את היסטוריית התשלומים שלה
    db.commit()
    return {"message": "תזכורת תשלום נמחקה"}


@router.post("/{payment_id}/mark-paid")
def mark_paid(
    payment_id: int,
    body: MarkPaid,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """מסמן שהמחזור הנוכחי שולם ורושם בהיסטוריה.
    חזרתית (שבועי/חודשי/שנתי): מתקדמת אוטומטית לתאריך היעד הבא.
    חד-פעמית (once): אין מחזור הבא — מסומנת is_active=False ויוצאת מהרשימה הפעילה,
    אבל ההיסטוריה שלה (PaymentLog) נשארת זמינה ב-GET /payments/{id}/history."""
    _require_parent(current_user)
    payment = db.query(RecurringPayment).filter(RecurringPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="תזכורת תשלום לא נמצאה")

    paid_period = payment.next_due_date
    amount_paid = body.amount_paid if body.amount_paid is not None else payment.amount

    db.add(PaymentLog(
        recurring_payment_id=payment.id,
        period_due_date=paid_period,
        amount_paid=amount_paid,
    ))

    if payment.recurrence == PaymentRecurrence.ONCE:
        payment.is_active = False
    else:
        payment.next_due_date = _advance_due_date(paid_period, payment.recurrence)
    db.commit()

    return {
        "message": "סומן ששולם",
        "paid_period": paid_period.isoformat(),
        "next_due_date": payment.next_due_date.isoformat(),
        "is_active": payment.is_active,
    }


@router.get("/{payment_id}/history")
def payment_history(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    payment = db.query(RecurringPayment).filter(RecurringPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="תזכורת תשלום לא נמצאה")

    logs = (
        db.query(PaymentLog)
        .filter(PaymentLog.recurring_payment_id == payment_id)
        .order_by(PaymentLog.paid_at.desc())
        .all()
    )
    return {
        "history": [
            {
                "id": log.id,
                "period_due_date": log.period_due_date.isoformat(),
                "amount_paid": log.amount_paid,
                "paid_at": log.paid_at.isoformat() if log.paid_at else None,
            }
            for log in logs
        ]
    }

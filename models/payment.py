"""
תזכורות תשלום — תשלומים שצריך לשלם כדי שלא ייווצר חוב או אי-נעימות (ארנונה, ביטוחים,
מנויים, אבל גם קנס או חוב חד-פעמי שחייבים לזכור לשלם).
כל תזכורת שומרת רק את "התאריך הבא לתשלום" (next_due_date) + סוג חזרתיות (recurrence).
חזרתית (שבועי/חודשי/שנתי): כשמסמנים "שולם" ה-due date מתקדם קדימה למחזור הבא —
ראו routers/payments.py:_advance_due_date.
חד-פעמית (once): כשמסמנים "שולם" היא הופכת ללא-פעילה (is_active=False) ויוצאת
מהרשימה הפעילה — אין מחזור הבא.
היסטוריית תשלומים בעבר נשמרת ב-PaymentLog, כדי שאפשר יהיה לראות "מה שולם ומתי".
"""
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base


class PaymentRecurrence(str, enum.Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    ONCE = "once"  # תשלום חד-פעמי — לא חוזר; מסומן לא-פעיל לאחר שסומן "שולם"


class RecurringPayment(Base):
    """תזכורת תשלום — חזרתית (למשל 'ארנונה' חודשי, 'ביטוח רכב' שנתי) או חד-פעמית
    (למשל קנס או חוב ספציפי שצריך לזכור לשלם פעם אחת)"""
    __tablename__ = "recurring_payments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    amount = Column(Float, nullable=True)  # אופציונלי — לא כל תשלום קבוע בסכום קבוע
    # VARCHAR רגיל ולא Postgres native enum בכוונה: enum מובנה ב-DB מחייב ALTER TYPE
    # ידני בכל הוספת ערך (וזה בדיוק מה שקרס בפרודקשן כשנוסף 'once' — ראו main.py).
    # הולידציה על הערכים התקפים נשארת בצד Python/Pydantic (PaymentRecurrence + routers/payments.py).
    recurrence = Column(String(20), nullable=False)
    next_due_date = Column(Date, nullable=False)
    remind_days_before = Column(Integer, nullable=False, default=3)
    notes = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    logs = relationship(
        "PaymentLog", back_populates="payment", cascade="all, delete-orphan",
        order_by="desc(PaymentLog.paid_at)",
    )


class PaymentLog(Base):
    """רישום היסטורי — שורה לכל פעם שסומן 'שולם' (לאיזה מחזור, באיזה סכום, מתי)"""
    __tablename__ = "payment_logs"

    id = Column(Integer, primary_key=True, index=True)
    recurring_payment_id = Column(Integer, ForeignKey("recurring_payments.id"), nullable=False)
    period_due_date = Column(Date, nullable=False)
    amount_paid = Column(Float, nullable=True)
    paid_at = Column(DateTime(timezone=True), server_default=func.now())

    payment = relationship("RecurringPayment", back_populates="logs")

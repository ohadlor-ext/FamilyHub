"""
תחזוקת הבית — מעקב אחרי כל דבר בבית שיש לו "תאריך שצריך לזכור": טיפול תקופתי במכשיר
(מזגן, דוד, רכב), אבל גם תוקף מסמך/ביטוח/אחריות (ביטוח דירה, רישוי רכב, אחריות על מקרר).
שני הסוגים האלה משתפים בדיוק את אותו צורך — "יש תאריך, צריך תזכורת לפניו, ואפשר
'לסגור' אותו" — ולכן מנוהלים כאן בטבלה אחת גנרית (MaintenanceItem). category הוא
שדה תצוגה/סינון בלבד (VARCHAR חופשי, לא enum — בכוונה, כדי לא לחזור על באג ה-ALTER
TYPE שקרה ב-recurring_payments.recurrence).

בשונה מ-RecurringPayment (recurrence קבוע: weekly/monthly/yearly), כאן יש מרווח גמיש
recurrence_interval_months (כל מספר חודשים — 1, 6, 12, 24...), כי טווחי תחזוקה אינם
אחידים (טיפול מזגן כל 6, ביטוח/רישוי כל 12). None = חד-פעמי (למשל תוקף אחריות שפג
ולא "מתחדש" — רק נסגר).
חזרתי: כשמסמנים "בוצע" next_due_date מתקדם ב-recurrence_interval_months חודשים.
חד-פעמי: כשמסמנים "בוצע"/"נסגר" הפריט הופך ללא-פעיל (is_active=False).
היסטוריה נשמרת ב-MaintenanceLog, בדיוק כמו PaymentLog.

בכוונה לא קיים שדה עלות/מחיר — בשונה מתשלומים, המטרה כאן היא לא לפספס תאריך,
לא לעקוב אחרי הוצאות. גם לא נשמרת תמונה — צילום משמש רק לחילוץ נתונים חד-פעמי
(services/claude_ai.py:identify_maintenance_item_from_photo), בדיוק כמו זיהוי תמונה
במלאי, כדי לא להוסיף תלות באחסון קבצים שלא קיימת בפרויקט.
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class MaintenanceItem(Base):
    """פריט תחזוקה/מסמך — מכשיר, רכב, ביטוח, מסמך, או אחר"""
    __tablename__ = "maintenance_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String(30), nullable=False, default="אחר")  # מכשיר/רכב/ביטוח/מסמך/אחר — לתצוגה בלבד
    next_due_date = Column(Date, nullable=False)
    recurrence_interval_months = Column(Integer, nullable=True)  # None = חד-פעמי
    remind_days_before = Column(Integer, nullable=False, default=14)
    provider_name = Column(String, nullable=True)  # טכנאי/חברה מועדפת
    provider_phone = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    logs = relationship(
        "MaintenanceLog", back_populates="item", cascade="all, delete-orphan",
        order_by="desc(MaintenanceLog.done_at)",
    )


class MaintenanceLog(Base):
    """רישום היסטורי — שורה לכל פעם שסומן 'בוצע'/'נסגר' (לאיזה תאריך יעד, מתי בפועל)"""
    __tablename__ = "maintenance_logs"

    id = Column(Integer, primary_key=True, index=True)
    maintenance_item_id = Column(Integer, ForeignKey("maintenance_items.id"), nullable=False)
    period_due_date = Column(Date, nullable=False)
    done_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("MaintenanceItem", back_populates="logs")

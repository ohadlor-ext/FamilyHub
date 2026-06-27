"""
לוח שגרה — צ'ק-ליסט בוקר/ערב פר ילד (לצחצח שיניים, להתלבש, לארוז תיק...).
האיפוס היומי לא דורש cron/scheduler: ההשלמה נשמרת לפי תאריך (RoutineCompletion.date),
אז כל יום חדש אין עדיין שורת השלמה — הצ'ק-ליסט "מתאפס" מעצמו.
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base


class RoutineType(str, enum.Enum):
    MORNING = "morning"
    EVENING = "evening"


class RoutineItem(Base):
    """פריט בודד בתבנית השגרה של ילד (למשל 'לצחצח שיניים') — התבנית עצמה, לא ההשלמה היומית"""
    __tablename__ = "routine_items"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    routine_type = Column(Enum(RoutineType), nullable=False)
    title = Column(String, nullable=False)
    emoji = Column(String, default="✅")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    completions = relationship(
        "RoutineCompletion", back_populates="item", cascade="all, delete-orphan"
    )


class RoutineCompletion(Base):
    """סימון 'בוצע' של פריט שגרה בתאריך מסוים — שורה לכל יום שסומן; אם אין שורה להיום, לא בוצע"""
    __tablename__ = "routine_completions"
    __table_args__ = (
        UniqueConstraint("routine_item_id", "date", name="uq_routine_completion_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    routine_item_id = Column(Integer, ForeignKey("routine_items.id"), nullable=False)
    date = Column(Date, nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("RoutineItem", back_populates="completions")

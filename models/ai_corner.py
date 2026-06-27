"""
פינת AI לילדים — תוכן מותאם אישית (סיפור לילה טוב, שאלות "למה?"/סקרנות, חידות
ובדיחות, רעיון ליצירה/ציור), עם שמירת מועדפים לילד ויומן צפייה להורה (פיקוח/בטיחות).

AICornerLog הוא מקור האמת היחיד לכל יצירה — גם בסיס ליומן ההורה (כל מה שנוצר,
לכל ילד, נראה להורה ב-GET /ai-corner/log) וגם המקור שממנו ילד שומר מועדף.
content_type הוא String רגיל (לא Postgres enum) בכוונה — ראו ההערה ב-main.py על
הבאג שגרם enum-ל-recurrence בתשלומים: הוספת ערך תוכן עתידי לא צריכה ALTER TYPE.

AICornerFavorite שומר snapshot של title/content בזמן השמירה (לא רק FK ל-log) —
כך מועדף נשאר תקין וקריא גם אם בעתיד ננקה רשומות לוג ישנות.

בטיחות תוכן: כמו בעוזר שיעורי הבית (services/claude_ai.py), אין דגל API מיוחד —
ההגנה היא פרומפט מערכת מחייב (גיל-מותאם, בלי תוכן בוגר/מפחיד) + ההכשרה הבטיחותית
המובנית של קלוד עצמו. עקביות עם התקדים הקיים באפליקציה.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class AICornerLog(Base):
    """כל יצירת תוכן בפינת ה-AI — מקור האמת היחיד ליומן הצפייה של ההורה."""
    __tablename__ = "ai_corner_logs"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content_type = Column(String(20), nullable=False)  # story / curiosity / riddle_joke / creative
    topic = Column(String, nullable=True)  # מה שהילד הקליד/ביקש (שאלה/נושא) — אם בכלל
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AICornerFavorite(Base):
    """תוכן ששמר ילד לקריאה/שימוש חזרה — snapshot עצמאי, לא תלוי בשרידות שורת הלוג."""
    __tablename__ = "ai_corner_favorites"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    log_id = Column(Integer, ForeignKey("ai_corner_logs.id"), nullable=True)
    content_type = Column(String(20), nullable=False)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

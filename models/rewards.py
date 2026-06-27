"""
תגמול ילדים על משימות ושגרה — מערכת נקודות גמישה:
ילד מקבל נקודות אוטומטית כשמשימה (Task) או פריט שגרה (RoutineItem) מסומן "בוצע",
וצובר יתרה שאפשר לממש מול קטלוג "תגמולים" שההורה מגדיר (קטלוג חופשי — יכול להיות
"30 דק' מסך", "5 ש״ח", "בחירת סרט" — לא מוגדר באפליקציה לאיזה סוג, המימוש בעולם
האמיתי הוא על ההורה; האפליקציה רק עוקבת אחרי הנקודות ורושמת מי מימש מה ומתי).

היתרה (balance) לא נשמרת כעמודה — היא מחושבת כסכום PointsTransaction.delta בזמן אמת
(services/rewards.py:get_balance), כדי שלא תהיה אף פעם דריפט בין "מה שנשמר" ל"מה
שבאמת קרה". היומן הוא מקור האמת היחיד, וגם נותן היסטוריה מלאה בלי טבלה נוספת.
תנועות שליליות (מימוש, ביטול סימון שגרה, ניכוי ידני) ותנועות חיוביות (זיכוי על
משימה/שגרה, בונוס ידני) — הכל נרשם כתנועה ב-PointsTransaction, אף פעם לא נמחק.

ערכי הנקודות (כמה מקבלים על משימה/פריט שגרה) מוגדרים ב-PointsConfig — שורה
יחידה (id=1) שנוצרת אוטומטית בפעם הראשונה שמישהו שואל אותה (get-or-create,
services/rewards.py:get_config), כדי שהורה יוכל לכוונן אותם בהגדרות בלי מיגרציה.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from database import Base


class PointsConfig(Base):
    """שורה יחידה (id=1) — כמה נקודות מקבלים על השלמת משימה / פריט שגרה אחד.
    ערך אחיד לכל סוג (כל המשימות שוות, כל פריטי השגרה שווים) — לא פר-פריט,
    בכוונה, כדי לא להעמיס מורכבות שלא נדרשה."""
    __tablename__ = "points_config"

    id = Column(Integer, primary_key=True, default=1)
    points_per_task = Column(Integer, nullable=False, default=10)
    points_per_routine_item = Column(Integer, nullable=False, default=5)


class PointsTransaction(Base):
    """יומן תנועות נקודות — מקור האמת היחיד ליתרה (ראו דוקסטרינג קובץ). append-only:
    גם ביטול/החזרה נרשם כתנועה הפוכה ולא כמחיקה, כדי לשמר היסטוריה מדויקת ומלאה."""
    __tablename__ = "points_transactions"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    delta = Column(Integer, nullable=False)  # חיובי = זיכוי, שלילי = חיוב/מימוש/ביטול
    source_type = Column(String(20), nullable=False)  # task / routine / manual / redemption
    source_id = Column(Integer, nullable=True)  # task_id / routine_item_id / reward_id — לפי source_type
    reason = Column(String, nullable=False)  # טקסט תצוגה — "השלמת משימה: ניקוי החדר" וכו'
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RewardCatalogItem(Base):
    """תגמול שניתן לממש בנקודות — ההורה קובע שם + מחיר בנקודות; הסוג (כסף/מסך/פעילות)
    הוא טקסט חופשי ולא נאכף באפליקציה בכוונה (ראו דוקסטרינג קובץ)."""
    __tablename__ = "reward_catalog_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    point_cost = Column(Integer, nullable=False)
    emoji = Column(String, default="🎁")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RewardRedemption(Base):
    """רישום היסטורי על כל מימוש — שם/מחיר נשמרים כ"צילום מצב" (snapshot) כדי
    שההיסטוריה תישאר נכונה גם אם התגמול נמחק/שונה בקטלוג לאחר מכן."""
    __tablename__ = "reward_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reward_id = Column(Integer, ForeignKey("reward_catalog_items.id"), nullable=True)
    reward_name = Column(String, nullable=False)
    point_cost = Column(Integer, nullable=False)
    redeemed_at = Column(DateTime(timezone=True), server_default=func.now())

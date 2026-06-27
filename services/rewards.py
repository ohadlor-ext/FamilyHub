"""
פונקציות עזר משותפות למערכת התגמולים — נקראות גם מ-routers/rewards.py (קטלוג/מימוש/
הגדרות) וגם מ-routers/tasks.py + routers/routines.py (כדי לזכות בנקודות בזמן השלמת
משימה/פריט שגרה). ראו models/rewards.py לדוקסטרינג המלא על העיצוב.

award_points בכוונה לא קוראת db.commit() בעצמה — הקריאה אליה קורית בתוך פונקציית
router שעושה commit אחד בסוף (לדוגמה: עדכון Task + זיכוי נקודות), כדי שהשניים
יקרו אטומית (אם אחד נכשל, גם השני לא נשמר).
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.rewards import PointsConfig, PointsTransaction


def get_config(db: Session) -> PointsConfig:
    """שורת ההגדרות היחידה (id=1) — נוצרת עם ערכי default בפעם הראשונה שמבקשים אותה."""
    config = db.query(PointsConfig).filter(PointsConfig.id == 1).first()
    if not config:
        config = PointsConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def get_balance(db: Session, child_id: int) -> int:
    """יתרת הנקודות של ילד — מחושבת מסכום היומן, לא נשמרת בנפרד (ראו דוקסטרינג קובץ המודלים)."""
    total = (
        db.query(func.coalesce(func.sum(PointsTransaction.delta), 0))
        .filter(PointsTransaction.child_id == child_id)
        .scalar()
    )
    return int(total or 0)


def award_points(
    db: Session,
    child_id: int,
    delta: int,
    source_type: str,
    reason: str,
    source_id: int = None,
):
    """מוסיף תנועה ליומן (db.add בלבד, לא commit — ראו דוקסטרינג קובץ)."""
    if delta == 0:
        return
    db.add(PointsTransaction(
        child_id=child_id,
        delta=delta,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
    ))

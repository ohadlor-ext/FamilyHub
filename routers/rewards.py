"""
תגמול ילדים על משימות ושגרה — ניהול קטלוג תגמולים, מימוש, יתרה/היסטוריה, בונוס ידני
והגדרות נקודות. זיכוי הנקודות עצמו קורה ב-routers/tasks.py ו-routers/routines.py
(דרך services/rewards.py) — הראוטר הזה הוא רק על הצד ה"מוציא" (קטלוג + מימוש)
וה"ניהולי" (כוונון ערכי נקודות, בונוס/ניכוי ידני). ראו models/rewards.py לדוקסטרינג
המלא על העיצוב (יתרה מחושבת מהיומן, לא נשמרת בנפרד).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.rewards import RewardCatalogItem, RewardRedemption, PointsTransaction
from routers.auth import get_current_user_dep
from services.rewards import get_config, get_balance, award_points
from services.notifications import notify_reward_redeemed

router = APIRouter(prefix="/rewards", tags=["rewards"])


def _require_parent(user: User):
    if user.role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="הורים בלבד")


class RewardCreate(BaseModel):
    name: str
    point_cost: int
    emoji: str = "🎁"


class RewardUpdate(BaseModel):
    name: Optional[str] = None
    point_cost: Optional[int] = None
    emoji: Optional[str] = None
    is_active: Optional[bool] = None


class RedeemRequest(BaseModel):
    child_id: int
    reward_id: int


class AdjustRequest(BaseModel):
    child_id: int
    delta: int
    reason: str


class ConfigUpdate(BaseModel):
    points_per_task: Optional[int] = None
    points_per_routine_item: Optional[int] = None


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """יתרה לכל ילד + קטלוג התגמולים הפעיל — למסך הקיוסק"""
    children = (
        db.query(User)
        .filter(User.role == UserRole.CHILD, User.is_active == True)
        .all()
    )
    children_data = []
    for child in children:
        profile = child.child_profile
        children_data.append({
            "child_id": child.id,
            "name": child.name,
            "avatar_emoji": (profile.avatar_emoji if profile else None) or "🧒",
            "color_theme": (profile.color_theme if profile else None) or "#6C63FF",
            "balance": get_balance(db, child.id),
        })

    catalog = (
        db.query(RewardCatalogItem)
        .filter(RewardCatalogItem.is_active == True)
        .order_by(RewardCatalogItem.point_cost)
        .all()
    )

    return {
        "children": children_data,
        "catalog": [
            {"id": r.id, "name": r.name, "point_cost": r.point_cost, "emoji": r.emoji}
            for r in catalog
        ],
    }


@router.get("/history")
def get_history(
    child_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """יתרה + יומן תנועות (זיכויים, מימושים, בונוסים) — למסך ההגדרות"""
    if current_user.role == UserRole.CHILD and child_id != current_user.id:
        raise HTTPException(status_code=403, detail="אין הרשאה")

    transactions = (
        db.query(PointsTransaction)
        .filter(PointsTransaction.child_id == child_id)
        .order_by(PointsTransaction.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "balance": get_balance(db, child_id),
        "transactions": [
            {
                "id": t.id,
                "delta": t.delta,
                "source_type": t.source_type,
                "reason": t.reason,
                "created_at": t.created_at,
            }
            for t in transactions
        ],
    }


@router.get("/catalog")
def list_catalog(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    query = db.query(RewardCatalogItem)
    if not include_inactive:
        query = query.filter(RewardCatalogItem.is_active == True)
    items = query.order_by(RewardCatalogItem.point_cost).all()
    return {
        "catalog": [
            {
                "id": r.id, "name": r.name, "point_cost": r.point_cost,
                "emoji": r.emoji, "is_active": r.is_active,
            }
            for r in items
        ]
    }


@router.post("/catalog")
def create_reward(
    data: RewardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    reward = RewardCatalogItem(**data.model_dump())
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return {"message": "תגמול נוסף", "id": reward.id}


@router.patch("/catalog/{reward_id}")
def update_reward(
    reward_id: int,
    update: RewardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    reward = db.query(RewardCatalogItem).filter(RewardCatalogItem.id == reward_id).first()
    if not reward:
        raise HTTPException(status_code=404, detail="תגמול לא נמצא")
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(reward, field, value)
    db.commit()
    return {"message": "תגמול עודכן"}


@router.delete("/catalog/{reward_id}")
def delete_reward(
    reward_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    reward = db.query(RewardCatalogItem).filter(RewardCatalogItem.id == reward_id).first()
    if not reward:
        raise HTTPException(status_code=404, detail="תגמול לא נמצא")
    db.delete(reward)  # היסטוריית מימושים עבר נשארת תקינה — RewardRedemption שומר snapshot
    db.commit()
    return {"message": "תגמול נמחק"}


@router.post("/redeem")
def redeem_reward(
    data: RedeemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """ילד (לעצמו) או הורה (בשם כל ילד) ממש תגמול — מנכה נקודות ורושם בהיסטוריה"""
    if current_user.role == UserRole.CHILD and data.child_id != current_user.id:
        raise HTTPException(status_code=403, detail="אין הרשאה")

    child = db.query(User).filter(
        User.id == data.child_id, User.role == UserRole.CHILD
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    reward = db.query(RewardCatalogItem).filter(
        RewardCatalogItem.id == data.reward_id, RewardCatalogItem.is_active == True
    ).first()
    if not reward:
        raise HTTPException(status_code=404, detail="תגמול לא נמצא או הוסר")

    balance = get_balance(db, child.id)
    if balance < reward.point_cost:
        raise HTTPException(
            status_code=400,
            detail=f"אין מספיק נקודות — יתרה {balance}, התגמול עולה {reward.point_cost}",
        )

    award_points(
        db, child.id, -reward.point_cost,
        "redemption", f"מימוש: {reward.name}", source_id=reward.id,
    )
    db.add(RewardRedemption(
        child_id=child.id, reward_id=reward.id,
        reward_name=reward.name, point_cost=reward.point_cost,
    ))
    db.commit()

    new_balance = get_balance(db, child.id)
    try:
        notify_reward_redeemed(child.name, reward.name, reward.point_cost, new_balance)
    except Exception:
        pass  # התראת טלגרם לא צריכה לשבור את המימוש אם היא נכשלת

    return {"message": "התגמול מומש", "new_balance": new_balance}


@router.post("/adjust")
def adjust_points(
    data: AdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הורה מוסיף/מחסיר נקודות ידנית — בונוס על התנהגות טובה, תיקון טעות וכו'
    (לא קשור לאוטומציה של משימות/שגרה — שכבת גמישות נוספת)"""
    _require_parent(current_user)
    child = db.query(User).filter(
        User.id == data.child_id, User.role == UserRole.CHILD
    ).first()
    if not child:
        raise HTTPException(status_code=404, detail="ילד לא נמצא")

    award_points(db, child.id, data.delta, "manual", data.reason)
    db.commit()
    return {"message": "היתרה עודכנה", "new_balance": get_balance(db, child.id)}


@router.get("/config")
def get_points_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    config = get_config(db)
    return {
        "points_per_task": config.points_per_task,
        "points_per_routine_item": config.points_per_routine_item,
    }


@router.patch("/config")
def update_points_config(
    update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    _require_parent(current_user)
    config = get_config(db)
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(config, field, value)
    db.commit()
    return {"message": "הגדרות הנקודות עודכנו"}

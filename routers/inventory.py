from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from database import get_db
from routers.auth import get_current_user_dep
from models.user import User
from models.inventory import InventoryItem, ShoppingListItem, InventoryUnit

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryItemCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    category: str = "כללי"
    quantity: float = 1
    unit: InventoryUnit = InventoryUnit.UNIT
    min_quantity: float = 1
    location: str = "מטבח"


class InventoryItemUpdate(BaseModel):
    quantity: Optional[float] = None
    on_shopping_list: Optional[bool] = None


@router.get("/")
def list_inventory(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    query = db.query(InventoryItem).filter(InventoryItem.is_active == True)
    if category:
        query = query.filter(InventoryItem.category == category)
    items = query.order_by(InventoryItem.category, InventoryItem.name).all()
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "quantity": item.quantity,
                "unit": item.unit,
                "min_quantity": item.min_quantity,
                "location": item.location,
                "low_stock": item.quantity <= item.min_quantity,
                "on_shopping_list": item.on_shopping_list,
                "barcode": item.barcode,
            }
            for item in items
        ]
    }


@router.post("/")
def add_item(
    item_data: InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    existing = None
    if item_data.barcode:
        existing = db.query(InventoryItem).filter(
            InventoryItem.barcode == item_data.barcode,
            InventoryItem.is_active == True,
        ).first()

    if existing:
        existing.quantity += item_data.quantity
        db.commit()
        return {"message": "כמות עודכנה", "item_id": existing.id}

    item = InventoryItem(**item_data.model_dump(), added_by=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)

    if item.quantity <= item.min_quantity:
        _add_to_shopping_list(db, item, current_user.id)

    return {"message": "פריט נוסף", "item_id": item.id}


@router.patch("/{item_id}")
def update_item(
    item_id: int,
    update_data: InventoryItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט לא נמצא")

    if update_data.quantity is not None:
        item.quantity = update_data.quantity
        if item.quantity <= item.min_quantity and not item.on_shopping_list:
            item.on_shopping_list = True
            _add_to_shopping_list(db, item, current_user.id)

    if update_data.on_shopping_list is not None:
        item.on_shopping_list = update_data.on_shopping_list

    db.commit()
    return {"message": "פריט עודכן"}


@router.get("/shopping")
def get_shopping_list(db: Session = Depends(get_db), _=Depends(get_current_user_dep)):
    items = db.query(ShoppingListItem).filter(
        ShoppingListItem.is_checked == False
    ).order_by(ShoppingListItem.category).all()
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "category": item.category,
                "is_checked": item.is_checked,
            }
            for item in items
        ],
        "count": len(items),
    }


@router.patch("/shopping/{item_id}/check")
def check_shopping_item(
    item_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    item = db.query(ShoppingListItem).filter(ShoppingListItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט לא נמצא")
    item.is_checked = True
    db.commit()
    return {"message": "פריט סומן כנרכש"}


def _add_to_shopping_list(db: Session, inventory_item: InventoryItem, user_id: int):
    needed = max(0, inventory_item.min_quantity - inventory_item.quantity)
    shopping_item = ShoppingListItem(
        name=inventory_item.name,
        quantity=needed or 1,
        unit=inventory_item.unit,
        category=inventory_item.category,
        inventory_item_id=inventory_item.id,
        added_by=user_id,
    )
    db.add(shopping_item)
    db.commit()

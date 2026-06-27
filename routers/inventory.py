import base64
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from PIL import Image
from database import get_db
from routers.auth import get_current_user_dep
from models.user import User
from models.inventory import InventoryItem, ShoppingListItem, InventoryUnit
from services.claude_ai import identify_product_from_photo, parse_receipt_photo
from services.notifications import notify_low_stock

router = APIRouter(prefix="/inventory", tags=["inventory"])

MAX_IMAGE_DIMENSION = 1568  # המלצת Anthropic — מקטין עלות טוקנים בלי לפגוע בזיהוי


def _process_image_upload(file: UploadFile) -> tuple:
    """קורא קובץ תמונה שהועלה, מקטין אם צריך, ומחזיר (base64, media_type)."""
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


class InventoryItemCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    category: str = "כללי"
    quantity: float = 1
    unit: InventoryUnit = InventoryUnit.UNIT
    min_quantity: float = 1
    location: str = "מטבח"


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[InventoryUnit] = None
    min_quantity: Optional[float] = None
    on_shopping_list: Optional[bool] = None


class ShoppingItemCreate(BaseModel):
    name: str
    quantity: float = 1
    unit: InventoryUnit = InventoryUnit.UNIT
    category: str = "כללי"


class ShoppingCheckRequest(BaseModel):
    actual_quantity: Optional[float] = None


class PhotoIdentifyResponse(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    confidence: Optional[str] = None


class ReceiptItemSuggestion(BaseModel):
    name: str
    quantity: float
    unit: str
    matched_existing: Optional[str] = None
    matched_item_id: Optional[int] = None


class ReceiptApplyItem(BaseModel):
    name: str
    quantity: float
    unit: InventoryUnit = InventoryUnit.UNIT
    category: str = "כללי"
    matched_item_id: Optional[int] = None


class ReceiptApplyRequest(BaseModel):
    items: List[ReceiptApplyItem]


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
        try:
            notify_low_stock(item.name)
        except Exception:
            pass

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

    if update_data.name is not None:
        item.name = update_data.name

    if update_data.category is not None:
        item.category = update_data.category

    if update_data.unit is not None:
        item.unit = update_data.unit

    if update_data.min_quantity is not None:
        item.min_quantity = update_data.min_quantity

    if update_data.quantity is not None:
        item.quantity = update_data.quantity
        if item.quantity <= item.min_quantity and not item.on_shopping_list:
            item.on_shopping_list = True
            _add_to_shopping_list(db, item, current_user.id)
            try:
                notify_low_stock(item.name)
            except Exception:
                pass

    if update_data.on_shopping_list is not None:
        item.on_shopping_list = update_data.on_shopping_list

    db.commit()
    return {"message": "פריט עודכן"}


@router.post("/shopping")
def add_shopping_item(
    item_data: ShoppingItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הוספת פריט לרשימת קניות בלבד — בלי ליצור/לעדכן פריט מלאי.
    זה מחליף את ההתנהגות הישנה שבה הוספת פריט קניות הייתה יוצרת בטעות
    פריט מלאי עם min_quantity=1, וגורמת לטריגר '_add_to_shopping_list' לרוץ
    על כל פריט מיד בלידתו."""
    item = ShoppingListItem(
        name=item_data.name,
        quantity=item_data.quantity,
        unit=item_data.unit,
        category=item_data.category,
        inventory_item_id=None,
        added_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"message": "פריט נוסף לרשימת קניות", "item_id": item.id}


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
                "inventory_item_id": item.inventory_item_id,
            }
            for item in items
        ],
        "count": len(items),
    }


@router.patch("/shopping/{item_id}/check")
def check_shopping_item(
    item_id: int,
    body: ShoppingCheckRequest = ShoppingCheckRequest(),
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    """מסמן פריט כנרכש. אם הפריט מקושר למלאי, מחזיר את הכמות שנקנתה בפועל
    למלאי (actual_quantity אם נשלח, אחרת הכמות המבוקשת המקורית)."""
    item = db.query(ShoppingListItem).filter(ShoppingListItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="פריט לא נמצא")
    item.is_checked = True

    if item.inventory_item_id:
        inv_item = db.query(InventoryItem).filter(InventoryItem.id == item.inventory_item_id).first()
        if inv_item:
            bought = body.actual_quantity if body.actual_quantity is not None else item.quantity
            inv_item.quantity += bought
            inv_item.last_purchased = datetime.now(timezone.utc)
            if inv_item.quantity > inv_item.min_quantity:
                inv_item.on_shopping_list = False

    db.commit()
    return {"message": "פריט סומן כנרכש"}


@router.post("/identify-photo", response_model=PhotoIdentifyResponse)
def identify_photo(
    file: UploadFile = File(...),
    _=Depends(get_current_user_dep),
):
    """מזהה מוצר בודד מתוך תמונה (Claude vision) — תחליף לסריקת ברקוד.
    לא כותב למלאי — מחזיר הצעה שהמשתמש מאשר/מתקן בפרונט לפני שמירה."""
    image_b64, media_type = _process_image_upload(file)
    result = identify_product_from_photo(image_b64, media_type)
    return PhotoIdentifyResponse(**result)


@router.post("/identify-receipt", response_model=List[ReceiptItemSuggestion])
def identify_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    """שולף פריטים+כמויות מתוך תמונת קבלה ומתאים לפריטי מלאי קיימים.
    לא כותב למלאי — מחזיר רשימת הצעות; אישור בפועל קורה ב-/identify-receipt/apply."""
    image_b64, media_type = _process_image_upload(file)
    existing_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    name_to_id = {item.name: item.id for item in existing_items}

    raw_results = parse_receipt_photo(image_b64, media_type, list(name_to_id.keys()))
    suggestions = []
    for r in raw_results:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        matched_name = r.get("matched_existing")
        suggestions.append(ReceiptItemSuggestion(
            name=r["name"],
            quantity=float(r.get("quantity") or 1),
            unit=r.get("unit") or "יחידות",
            matched_existing=matched_name,
            matched_item_id=name_to_id.get(matched_name) if matched_name else None,
        ))
    return suggestions


@router.post("/identify-receipt/apply")
def apply_receipt_items(
    body: ReceiptApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """מאשר בבת אחת את פריטי הקבלה: מעדכן כמות לפריטים מותאמים,
    ויוצר פריט מלאי חדש לכל פריט שלא נמצאה לו התאמה."""
    updated, created = 0, 0
    for entry in body.items:
        if entry.matched_item_id:
            inv_item = db.query(InventoryItem).filter(InventoryItem.id == entry.matched_item_id).first()
            if inv_item:
                inv_item.quantity += entry.quantity
                inv_item.last_purchased = datetime.now(timezone.utc)
                if inv_item.quantity > inv_item.min_quantity:
                    inv_item.on_shopping_list = False
                updated += 1
                continue
        new_item = InventoryItem(
            name=entry.name,
            category=entry.category,
            quantity=entry.quantity,
            unit=entry.unit,
            added_by=current_user.id,
            last_purchased=datetime.now(timezone.utc),
        )
        db.add(new_item)
        created += 1
    db.commit()
    return {"message": "מלאי עודכן", "updated": updated, "created": created}


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

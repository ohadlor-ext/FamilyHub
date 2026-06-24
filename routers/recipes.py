"""
הצעת מתכונים — מבוססת על המלאי החי בבית + העדפות האוכל של הילדים.
שני מצבים:
- /daily: הצעה אוטומטית לקיוסק, אחת ליום (נשמרת ב-DB כדי לא להשתנות בכל רענון)
- /suggest: "מה לבשל הערב?" — הצעה טרייה בכל לחיצה, לא נשמרת
מצרכים חסרים אפשר לאשר ב-/confirm-missing — נוספים לרשימת הקניות.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import get_current_user_dep
from models.user import User, ChildProfile
from models.inventory import InventoryItem, ShoppingListItem, InventoryUnit
from models.recipe import RecipeSuggestion
from services.claude_ai import get_recipe_suggestion

router = APIRouter(prefix="/recipes", tags=["recipes"])


class IngredientOut(BaseModel):
    name: str
    quantity: float
    unit: str
    have_in_inventory: bool


class RecipeOut(BaseModel):
    title: str
    description: str
    prep_time_minutes: Optional[int] = None
    servings: Optional[int] = None
    ingredients: List[IngredientOut]
    missing_ingredients: List[IngredientOut]
    instructions: List[str]


class MissingIngredientConfirm(BaseModel):
    name: str
    quantity: float = 1
    unit: InventoryUnit = InventoryUnit.UNIT


class ConfirmMissingRequest(BaseModel):
    items: List[MissingIngredientConfirm]


def _active_inventory(db: Session) -> List[InventoryItem]:
    return db.query(InventoryItem).filter(InventoryItem.is_active == True).all()


def _gather_preferences(db: Session) -> List[str]:
    preferences: List[str] = []
    for child in db.query(ChildProfile).all():
        if child.food_preferences:
            preferences.extend(child.food_preferences)
    return preferences


def _inventory_for_prompt(items: List[InventoryItem]) -> list:
    return [
        {
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit.value if hasattr(item.unit, "value") else item.unit,
            "category": item.category,
        }
        for item in items
    ]


def _build_recipe_out(raw: dict) -> RecipeOut:
    ingredients, missing = [], []
    for ing in raw.get("ingredients") or []:
        item = IngredientOut(
            name=ing.get("name", ""),
            quantity=float(ing.get("quantity") or 1),
            unit=ing.get("unit") or "יחידות",
            have_in_inventory=bool(ing.get("have_in_inventory")),
        )
        ingredients.append(item)
        if not item.have_in_inventory:
            missing.append(item)
    return RecipeOut(
        title=raw.get("title") or "מתכון",
        description=raw.get("description") or "",
        prep_time_minutes=raw.get("prep_time_minutes"),
        servings=raw.get("servings"),
        ingredients=ingredients,
        missing_ingredients=missing,
        instructions=raw.get("instructions") or [],
    )


@router.post("/suggest", response_model=RecipeOut)
def suggest_recipe(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """'מה לבשל הערב?' — הצעה חדשה בכל קריאה, לא נשמרת."""
    inventory_items = _active_inventory(db)
    preferences = _gather_preferences(db)
    raw = get_recipe_suggestion(
        inventory_items=_inventory_for_prompt(inventory_items),
        preferences=preferences,
    )
    return _build_recipe_out(raw)


@router.get("/daily", response_model=RecipeOut)
def daily_recipe(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """הצעה יומית אוטומטית לקיוסק — נשמרת לאותו תאריך כדי לא להשתנות בכל רענון."""
    today = date.today()
    cached = db.query(RecipeSuggestion).filter(RecipeSuggestion.suggestion_date == today).first()
    if cached:
        return _build_recipe_out({
            "title": cached.title,
            "description": cached.description,
            "prep_time_minutes": cached.prep_time_minutes,
            "servings": cached.servings,
            "ingredients": cached.ingredients,
            "instructions": cached.instructions,
        })

    inventory_items = _active_inventory(db)
    preferences = _gather_preferences(db)
    raw = get_recipe_suggestion(
        inventory_items=_inventory_for_prompt(inventory_items),
        preferences=preferences,
    )

    record = RecipeSuggestion(
        suggestion_date=today,
        title=raw.get("title") or "מתכון",
        description=raw.get("description") or "",
        prep_time_minutes=raw.get("prep_time_minutes"),
        servings=raw.get("servings"),
        ingredients=raw.get("ingredients") or [],
        instructions=raw.get("instructions") or [],
    )
    db.add(record)
    db.commit()

    return _build_recipe_out(raw)


@router.post("/confirm-missing")
def confirm_missing(
    body: ConfirmMissingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """מוסיף לרשימת הקניות את המצרכים החסרים שהמשתמש אישר."""
    added = 0
    for entry in body.items:
        existing = db.query(InventoryItem).filter(
            InventoryItem.name == entry.name, InventoryItem.is_active == True
        ).first()
        item = ShoppingListItem(
            name=entry.name,
            quantity=entry.quantity,
            unit=entry.unit,
            category=existing.category if existing else "כללי",
            inventory_item_id=existing.id if existing else None,
            added_by=current_user.id,
        )
        db.add(item)
        added += 1
    db.commit()
    return {"message": "נוספו לרשימת הקניות", "added": added}

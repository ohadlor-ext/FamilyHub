"""
תכנון ארוחות שבועי + מאגר מתכונים.
שונה מ-routers/recipes.py: שם המתכון "טרי" בכל קריאה ונעלם (AI על המלאי הרגעי),
כאן המתכון קבוע במאגר (Recipe) ומשובץ ליום מסוים בשבוע (MealPlan).
גרסה ראשונה: ארוחות ערב בלבד (meal_type=dinner), אבל הסכמה לא קשיחה לזה.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import get_current_user_dep
from models.user import User
from models.recipe import Recipe, MealPlan, MealType, RecipeSource
from routers.recipes import _active_inventory

router = APIRouter(prefix="/meal-plans", tags=["meal-plans"])


# ---------- סכמות ----------

class RecipeIn(BaseModel):
    title: str
    description: Optional[str] = None
    meal_type: MealType = MealType.DINNER
    prep_time_minutes: Optional[int] = None
    servings: Optional[int] = 4
    ingredients: List[dict] = []  # [{name, quantity, unit}]
    instructions: List[str] = []
    tags: List[str] = []


class MealPlanUpsert(BaseModel):
    plan_date: date
    meal_type: MealType = MealType.DINNER
    recipe_id: Optional[int] = None
    notes: Optional[str] = None


def _recipe_to_dict(recipe: Recipe) -> Optional[dict]:
    if not recipe:
        return None
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "meal_type": recipe.meal_type,
        "prep_time_minutes": recipe.prep_time_minutes,
        "servings": recipe.servings,
        "ingredients": recipe.ingredients,
        "instructions": recipe.instructions,
        "tags": recipe.tags,
        "source": recipe.source,
    }


# ---------- מאגר מתכונים ----------

@router.get("/recipes")
def list_recipes(
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    """כל המתכונים הפעילים במאגר — לבחירה בתכנון השבוע. tag מסנן לפי תגית בודדת."""
    recipes = db.query(Recipe).filter(Recipe.is_active == True).order_by(Recipe.title).all()
    if tag:
        recipes = [r for r in recipes if r.tags and tag in r.tags]
    return {"recipes": [_recipe_to_dict(r) for r in recipes], "count": len(recipes)}


@router.post("/recipes")
def create_recipe(
    body: RecipeIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    """הוספת מתכון משפחתי למאגר (לא seed/AI)."""
    recipe = Recipe(
        title=body.title,
        description=body.description,
        meal_type=body.meal_type,
        prep_time_minutes=body.prep_time_minutes,
        servings=body.servings,
        ingredients=body.ingredients,
        instructions=body.instructions,
        tags=body.tags,
        source=RecipeSource.FAMILY,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _recipe_to_dict(recipe)


# ---------- תכנון שבועי ----------

def _week_bounds(start: Optional[date]) -> date:
    """ברירת מחדל: יום ראשון הקרוב (כולל היום אם היום ראשון) — תחילת השבוע הישראלי."""
    if start:
        return start
    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7  # weekday(): Monday=0 ... Sunday=6
    return today - timedelta(days=days_since_sunday)


@router.get("/week")
def get_week_plan(
    start: Optional[date] = Query(default=None, description="תאריך תחילת השבוע (יום ראשון). אם לא צוין — השבוע הנוכחי"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    week_start = _week_bounds(start)
    week_end = week_start + timedelta(days=6)

    plans = db.query(MealPlan).filter(
        MealPlan.plan_date >= week_start,
        MealPlan.plan_date <= week_end,
        MealPlan.meal_type == MealType.DINNER,  # v1: ארוחות ערב בלבד
    ).all()
    plans_by_date = {p.plan_date: p for p in plans}

    recipe_ids = {p.recipe_id for p in plans if p.recipe_id}
    recipes_by_id = {}
    if recipe_ids:
        for r in db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all():
            recipes_by_id[r.id] = r

    days = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        plan = plans_by_date.get(day)
        days.append({
            "date": day.isoformat(),
            "meal_type": MealType.DINNER,
            "plan_id": plan.id if plan else None,
            "recipe": _recipe_to_dict(recipes_by_id.get(plan.recipe_id)) if plan and plan.recipe_id else None,
            "notes": plan.notes if plan else None,
        })

    return {"start": week_start.isoformat(), "end": week_end.isoformat(), "days": days}


@router.post("/")
def upsert_meal_plan(
    body: MealPlanUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """משבץ/מעדכן מתכון ליום מסוים. אם כבר יש שיבוץ לאותו תאריך+סוג ארוחה — מעדכן אותו."""
    if body.recipe_id:
        recipe = db.query(Recipe).filter(Recipe.id == body.recipe_id, Recipe.is_active == True).first()
        if not recipe:
            raise HTTPException(status_code=404, detail="מתכון לא נמצא")

    plan = db.query(MealPlan).filter(
        MealPlan.plan_date == body.plan_date,
        MealPlan.meal_type == body.meal_type,
    ).first()

    if plan:
        plan.recipe_id = body.recipe_id
        plan.notes = body.notes
    else:
        plan = MealPlan(
            plan_date=body.plan_date,
            meal_type=body.meal_type,
            recipe_id=body.recipe_id,
            notes=body.notes,
            created_by=current_user.id,
        )
        db.add(plan)

    db.commit()
    db.refresh(plan)
    return {
        "id": plan.id,
        "plan_date": plan.plan_date.isoformat(),
        "meal_type": plan.meal_type,
        "recipe": _recipe_to_dict(plan.recipe) if plan.recipe_id else None,
        "notes": plan.notes,
    }


@router.delete("/{plan_id}")
def delete_meal_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    plan = db.query(MealPlan).filter(MealPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="שיבוץ לא נמצא")
    db.delete(plan)
    db.commit()
    return {"message": "השיבוץ נוקה"}


# ---------- רשימת קניות לפי השבוע ----------

@router.get("/week/missing-ingredients")
def week_missing_ingredients(
    start: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user_dep),
):
    """מצרף את כל המצרכים מהמתכונים המשובצים לשבוע, ומשווה למלאי החי.
    מחזיר רשימת חוסרים בפורמט שמתאים בדיוק ל-POST /recipes/confirm-missing הקיים —
    הפרונט שולח את אותה רשימה לשם כדי בפועל להוסיף לרשימת הקניות (אין כפילות לוגיקה)."""
    week_start = _week_bounds(start)
    week_end = week_start + timedelta(days=6)

    plans = db.query(MealPlan).filter(
        MealPlan.plan_date >= week_start,
        MealPlan.plan_date <= week_end,
        MealPlan.recipe_id.isnot(None),
    ).all()

    recipe_ids = {p.recipe_id for p in plans}
    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all() if recipe_ids else []

    needed: dict = {}  # name -> {"quantity": float, "unit": str}
    for recipe in recipes:
        for ing in recipe.ingredients or []:
            name = ing.get("name")
            if not name:
                continue
            qty = float(ing.get("quantity") or 0)
            unit = ing.get("unit") or "יחידות"
            if name in needed:
                needed[name]["quantity"] += qty
            else:
                needed[name] = {"quantity": qty, "unit": unit}

    inventory_by_name = {item.name: item.quantity for item in _active_inventory(db)}

    missing = []
    for name, info in needed.items():
        have = inventory_by_name.get(name, 0)
        if have < info["quantity"]:
            missing.append({
                "name": name,
                "quantity": round(info["quantity"] - have, 2),
                "unit": info["unit"],
            })

    return {"start": week_start.isoformat(), "end": week_end.isoformat(), "missing": missing}

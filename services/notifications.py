"""
התראות יזומות למשפחה בטלגרם — V1: דחיפה בלבד (אין עדיין פקודות דו-כיווניות).

שני סוגי טריגר:
- מתוזמן (קרון, מוגדר ב-main.py): סיכום בוקר + הצעת מתכון יומית.
- בזמן אמת (נקרא מתוך routers): משימה חדשה, פריט שנגמר/נמוך במלאי.

כל הפונקציות כאן סינכרוניות בכוונה — נקראות גם מתוך routes רגילים (def) וגם
מתוך jobs של APScheduler, ופותחות session משלהן ל-DB כשרצות מחוץ להקשר של request.
"""
import asyncio
import logging
from datetime import datetime

from database import SessionLocal
from models.task import Task, TaskStatus
from models.user import ChildProfile
from models.inventory import InventoryItem
from services.telegram_bot import send_message_sync
from services.icloud_calendar import get_today_events
from services.openweather import get_current_weather
from services.claude_ai import get_recipe_suggestion

logger = logging.getLogger(__name__)

_WEEKDAY_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def _unit_value(unit):
    return unit.value if hasattr(unit, "value") else unit


def send_morning_summary():
    """נשלח כל בוקר (קרון ב-main.py, 07:30) — מה קורה היום: יומן + משימות פתוחות + מזג אוויר."""
    db = SessionLocal()
    try:
        lines = [f"☀️ *בוקר טוב משפחה!* יום {_WEEKDAY_HE[datetime.now().weekday()]}"]

        try:
            events = get_today_events()
        except Exception as e:
            logger.error(f"send_morning_summary: שגיאה בשליפת יומן: {e}")
            events = []
        if events:
            lines.append("\n📅 *היום ביומן:*")
            for e in events[:5]:
                lines.append(f"  • {e.get('title', 'אירוע')}")
        else:
            lines.append("\n📅 אין אירועים ביומן היום")

        try:
            open_tasks = (
                db.query(Task)
                .filter(Task.status != TaskStatus.DONE)
                .order_by(Task.due_date.asc().nullslast())
                .limit(5)
                .all()
            )
        except Exception as e:
            logger.error(f"send_morning_summary: שגיאה בשליפת משימות: {e}")
            open_tasks = []
        if open_tasks:
            lines.append("\n✅ *משימות פתוחות:*")
            for t in open_tasks:
                who = f" ({t.assigned_to_user.name})" if t.assigned_to_user else ""
                lines.append(f"  • {t.title}{who}")

        try:
            weather = asyncio.run(get_current_weather())
            lines.append(f"\n{weather['icon']} *מזג אוויר:* {weather['temp']}°C, {weather['description']}")
        except Exception as e:
            logger.error(f"send_morning_summary: שגיאה בשליפת מזג אוויר: {e}")

        send_message_sync("\n".join(lines))
    finally:
        db.close()


def send_recipe_notification():
    """נשלח אחה"צ (קרון ב-main.py, 16:00) — הצעת המתכון היומי, אותה לוגיקה שמזינה
    את /recipes/daily בקיוסק (מלאי חי + העדפות אוכל של הילדים)."""
    db = SessionLocal()
    try:
        items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
        preferences = []
        for child in db.query(ChildProfile).all():
            if child.food_preferences:
                preferences.extend(child.food_preferences)

        inventory_for_prompt = [
            {
                "name": i.name,
                "quantity": i.quantity,
                "unit": _unit_value(i.unit),
                "category": i.category,
            }
            for i in items
        ]
        recipe = get_recipe_suggestion(inventory_items=inventory_for_prompt, preferences=preferences)

        title = recipe.get("title") or "מתכון"
        desc = recipe.get("description") or ""
        msg = f"🍽️ *מה לבשל הערב?*\n\n*{title}*\n{desc}"
        send_message_sync(msg)
    except Exception as e:
        logger.error(f"send_recipe_notification נכשל: {e}")
    finally:
        db.close()


def notify_new_task(task_title: str, assigned_name: str = None, due_date=None):
    """נשלח בזמן אמת כשנוצרת משימה חדשה (נקרא מתוך routers/tasks.py)."""
    who = f" ל{assigned_name}" if assigned_name else ""
    when = f" (עד {due_date.strftime('%d/%m')})" if due_date else ""
    send_message_sync(f"📝 משימה חדשה{who}: *{task_title}*{when}")


def notify_low_stock(item_name: str):
    """נשלח בזמן אמת כשפריט חוצה את כמות המינימום ונוסף לרשימת הקניות
    (נקרא מתוך routers/inventory.py)."""
    send_message_sync(f"🛒 נגמר/נמוך במלאי: *{item_name}* — נוסף לרשימת הקניות")

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
from zoneinfo import ZoneInfo

from database import SessionLocal
from models.task import Task, TaskStatus
from models.user import ChildProfile
from models.inventory import InventoryItem
from models.payment import RecurringPayment
from models.maintenance import MaintenanceItem
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


def send_payment_reminders():
    """נשלח כל בוקר (קרון ב-main.py, 08:00) — תזכורת מאוחדת אחת על כל תשלום (חזרתי או
    חד-פעמי) שמתקרב/הגיע/עבר את תאריך היעד שלו, כדי שלא ייווצר חוב או אי-נעימות.
    תשלום שעבר את התאריך ולא סומן 'שולם' יחזור להופיע כל יום (overdue) עד שיסמנו
    אותו — בכוונה, כדי שלא יישכח."""
    db = SessionLocal()
    try:
        today = datetime.now(ZoneInfo("Asia/Jerusalem")).date()
        payments = db.query(RecurringPayment).filter(RecurringPayment.is_active == True).all()

        overdue, due_today, due_soon = [], [], []
        for p in payments:
            days_until = (p.next_due_date - today).days
            if days_until < 0:
                overdue.append((p, days_until))
            elif days_until == 0:
                due_today.append(p)
            elif days_until == p.remind_days_before:
                due_soon.append((p, days_until))

        if not (overdue or due_today or due_soon):
            return  # אין מה להזכיר היום — לא שולחת הודעה בכלל

        lines = ["💰 *תזכורות תשלום*"]

        if overdue:
            lines.append("\n🔴 *באיחור:*")
            for p, days_until in overdue:
                amount = f" ({p.amount:.0f}₪)" if p.amount else ""
                lines.append(f"  • {p.title}{amount} — באיחור של {abs(days_until)} ימים")

        if due_today:
            lines.append("\n🟠 *היום מועד התשלום:*")
            for p in due_today:
                amount = f" ({p.amount:.0f}₪)" if p.amount else ""
                lines.append(f"  • {p.title}{amount}")

        if due_soon:
            lines.append("\n🟡 *מתקרב:*")
            for p, days_until in due_soon:
                amount = f" ({p.amount:.0f}₪)" if p.amount else ""
                lines.append(f"  • {p.title}{amount} — בעוד {days_until} ימים")

        send_message_sync("\n".join(lines))
    except Exception as e:
        logger.error(f"send_payment_reminders נכשל: {e}")
    finally:
        db.close()


def send_maintenance_reminders():
    """נשלח כל בוקר (קרון ב-main.py, 08:05) — תזכורת מאוחדת אחת על כל פריט תחזוקת
    הבית (מכשיר/רכב/ביטוח/מסמך) שמתקרב/הגיע/עבר את תאריך היעד שלו.
    פריט שעבר את התאריך ולא סומן 'בוצע' יחזור להופיע כל יום (overdue) עד שיסמנו
    אותו — בכוונה, כדי שלא יישכח (אותה לוגיקה כמו send_payment_reminders)."""
    db = SessionLocal()
    try:
        today = datetime.now(ZoneInfo("Asia/Jerusalem")).date()
        items = db.query(MaintenanceItem).filter(MaintenanceItem.is_active == True).all()

        overdue, due_today, due_soon = [], [], []
        for item in items:
            days_until = (item.next_due_date - today).days
            if days_until < 0:
                overdue.append((item, days_until))
            elif days_until == 0:
                due_today.append(item)
            elif days_until == item.remind_days_before:
                due_soon.append((item, days_until))

        if not (overdue or due_today or due_soon):
            return  # אין מה להזכיר היום — לא שולחת הודעה בכלל

        lines = ["🔧 *תחזוקת הבית*"]

        if overdue:
            lines.append("\n🔴 *באיחור:*")
            for item, days_until in overdue:
                lines.append(f"  • {item.name} — באיחור של {abs(days_until)} ימים")

        if due_today:
            lines.append("\n🟠 *היום מועד הטיפול/החידוש:*")
            for item in due_today:
                lines.append(f"  • {item.name}")

        if due_soon:
            lines.append("\n🟡 *מתקרב:*")
            for item, days_until in due_soon:
                lines.append(f"  • {item.name} — בעוד {days_until} ימים")

        send_message_sync("\n".join(lines))
    except Exception as e:
        logger.error(f"send_maintenance_reminders נכשל: {e}")
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


def notify_reward_redeemed(child_name: str, reward_name: str, point_cost: int, new_balance: int):
    """נשלח בזמן אמת כשילד ממש תגמול מהקטלוג (נקרא מתוך routers/rewards.py).
    בכוונה אין התראה מקבילה על כל זיכוי נקודות (משימה/שגרה) — זה יהיה רעשני
    מאוד (כל צ'ק-בוקס שגרה), בניגוד למימוש שהוא אירוע נדיר וחשוב יותר להורה."""
    send_message_sync(
        f"🎁 {child_name} מימש/ה: *{reward_name}* ({point_cost} נקודות) — יתרה נשארה: {new_balance}"
    )

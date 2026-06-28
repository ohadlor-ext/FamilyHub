"""
Telegram → רשומה: כיוון הפוך מ-services/telegram_bot.py (שזה רק יוצא/דחיפה).
כאן נכנסות הודעות שבני המשפחה שולחים *לתוך* הקבוצה, ו-AI (Claude) מסווג כל הודעה
לאחת מחמש קטגוריות — event (אירוע ליומן), payment (תשלום), maintenance (תחזוקת בית),
task (משימה), או none (לא רלוונטי) — ויוצר את הרשומה המתאימה בהתאם.

זרימה:
1. Telegram שולח כל הודעה חדשה בקבוצה ל-POST /telegram/webhook (לאחר שמגדירים
   setWebhook חד-פעמי מול ה-API של טלגרם — ראו הוראות בהודעת הקומיט).
2. מאמתים שההודעה הגיעה מה-chat_id המוכר (TELEGRAM_FAMILY_CHAT_ID) ומה-secret
   token הנכון (TELEGRAM_WEBHOOK_SECRET, אם הוגדר) — כדי שלא כל גורם מהאינטרנט
   שמוצא את כתובת ה-webhook יוכל ליצור רשומות.
3. אם יש הצעה שמחכה לאישור מהודעה קודמת באותו chat — בודקים אם ההודעה הנוכחית
   היא תשובת כן/לא לה. אם לא, ההצעה הקודמת מתיישנת ומטופלת כהודעה רגילה.
4. קוראים ל-Claude (services/claude_ai.parse_telegram_message) לסנן/לסווג/לחלץ.
   אם category="none" — לא מגיבים בכלל (כדי לא להציף את קבוצת המשפחה). אם
   בביטחון גבוה — נוצרת הרשומה אוטומטית. אם ביטחון בינוני/נמוך — שולחים שאלת
   אישור (ניסוח לפי קטגוריה) ושומרים את ההצעה בזיכרון עד לתשובה.
5. לפי category נוצרת הרשומה במקום המתאים: task → models.task.Task,
   event → יומן ה-iCloud (services/icloud_calendar.create_event),
   payment → models.payment.RecurringPayment, maintenance → models.maintenance.MaintenanceItem.

הערה: מצב ה"הצעה שמחכה לאישור" נשמר בזיכרון התהליך (לא ב-DB) — פיצ'ר קליל
בכוונה, כמו שאר ההתראות בקובץ הזה. אם השרת נדחק/קם מחדש בדיוק בין הודעת
ההצעה לתשובה, ההצעה תאבד וההודעה הבאה תיבדק מהתחלה — תופעת לוואי מקובלת לV1.
"""
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Header

from database import SessionLocal
from models.user import User, UserRole
from models.task import Task, TaskPriority
from models.payment import RecurringPayment
from models.maintenance import MaintenanceItem
from services.telegram_bot import send_message_sync
from services.claude_ai import parse_telegram_message
from services.icloud_calendar import create_event as create_calendar_event

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

FAMILY_CHAT_ID = os.getenv("TELEGRAM_FAMILY_CHAT_ID")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

_CONFIRM_WORDS = {"כן", "אישור", "מאשר", "מאשרת", "yes", "y", "ok", "אוקיי", "👍", "✅"}
_CANCEL_WORDS = {"לא", "ביטול", "בטל", "no", "n", "cancel", "👎"}

_VALID_RECURRENCE = {"once", "weekly", "monthly", "yearly"}
_VALID_MAINTENANCE_CATEGORIES = {"מכשיר", "רכב", "ביטוח", "מסמך", "אחר"}
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# הצעה שמחכה לאישור, לפי chat_id — ראו services/claude_ai.parse_telegram_message
# למבנה המלא (category/title/date/end_date/all_day/location/assigned_name/amount/
# recurrence/maintenance_category).
_pending: dict[str, dict] = {}


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=None),
):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        logger.warning("Telegram webhook: secret token לא תואם — ההודעה נדחתה")
        return {"ok": True}

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    message = body.get("message") or body.get("edited_message")
    if not message or not message.get("text"):
        return {"ok": True}  # סטיקרים/תמונות/הודעות קול/וכו' — לא רלוונטי לפיצ'ר הזה

    chat_id = str(message["chat"]["id"])
    text = message["text"].strip()
    sender = message.get("from") or {}
    sender_name = sender.get("first_name") or sender.get("username") or "מישהו מהמשפחה"

    if FAMILY_CHAT_ID and chat_id != str(FAMILY_CHAT_ID):
        logger.warning(f"Telegram webhook: הודעה מ-chat_id לא מוכר ({chat_id}) — נדחתה")
        return {"ok": True}

    # תשובה להצעה קודמת שמחכה באותו צ'אט?
    pending = _pending.get(chat_id)
    if pending:
        normalized = text.strip().lower()
        if text in _CONFIRM_WORDS or normalized in _CONFIRM_WORDS:
            del _pending[chat_id]
            _create_record_from_suggestion(pending, chat_id)
            return {"ok": True}
        if text in _CANCEL_WORDS or normalized in _CANCEL_WORDS:
            del _pending[chat_id]
            send_message_sync("בסדר, לא נוסף.", chat_id=chat_id)
            return {"ok": True}
        # לא תגובת כן/לא — ההצעה הקודמת התיישנה, ממשיכים לטפל בהודעה הזו מהתחלה
        del _pending[chat_id]

    db = SessionLocal()
    try:
        family_names = [u.name for u in db.query(User).filter(User.is_active == True).all()]
    finally:
        db.close()

    now = datetime.now(ISRAEL_TZ)
    try:
        result = parse_telegram_message(text, family_member_names=family_names, sender_name=sender_name, now=now)
    except Exception as e:
        logger.error(f"Telegram webhook: parse_telegram_message נכשל: {e}")
        return {"ok": True}

    category = result.get("category") or "none"
    if category == "none":
        return {"ok": True}  # לא רלוונטי — בכוונה לא מגיבים, כדי לא להציף את הקבוצה

    suggestion = {
        "category": category,
        "title": (result.get("title") or text).strip(),
        "date": result.get("date"),
        "end_date": result.get("end_date"),
        "all_day": bool(result.get("all_day")),
        "location": result.get("location"),
        "assigned_name": result.get("assigned_name"),
        "amount": result.get("amount"),
        "recurrence": result.get("recurrence") or "once",
        "maintenance_category": result.get("maintenance_category") or "אחר",
    }

    # רשת ביטחון: event/payment/maintenance בלי תאריך קונקרטי אינם תקפים — מבוטח
    # גם כשה-AI לא הקפיד על ההנחיה לסווג כ-task במקרה הזה (ראו prompt בclaude_ai.py).
    if suggestion["category"] in ("event", "payment", "maintenance") and not suggestion["date"]:
        suggestion["category"] = category = "task"

    if result.get("confidence") == "high":
        _create_record_from_suggestion(suggestion, chat_id)
    else:
        _pending[chat_id] = suggestion
        send_message_sync(_confirmation_text(suggestion), chat_id=chat_id)

    return {"ok": True}


def _parse_dt(iso_str):
    """ממיר מחרוזת ISO (כמו שה-AI מחזיר) ל-datetime מודע-אזור-זמן (Asia/Jerusalem).
    מחזיר None אם המחרוזת חסרה/לא תקינה."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str).replace(tzinfo=ISRAEL_TZ)
    except ValueError:
        return None


def _format_when(iso_str, all_day=False) -> str:
    dt = _parse_dt(iso_str)
    if not dt:
        return ""
    return f" ב-{dt.strftime('%d/%m')}" if all_day else f" ב-{dt.strftime('%d/%m %H:%M')}"


def _confirmation_text(suggestion: dict) -> str:
    category = suggestion["category"]
    title = suggestion["title"]

    if category == "event":
        when = _format_when(suggestion["date"], suggestion.get("all_day"))
        where = f" ב{suggestion['location']}" if suggestion.get("location") else ""
        return f"🤔 להוסיף ליומן: *{title}*{when}{where}?\nענו \"כן\" לאישור או \"לא\" לביטול."

    if category == "payment":
        when = _format_when(suggestion["date"])
        amount = f" ({suggestion['amount']:.0f} ש\"ח)" if suggestion.get("amount") else ""
        return f"🤔 להוסיף תזכורת תשלום: *{title}*{amount}{when}?\nענו \"כן\" לאישור או \"לא\" לביטול."

    if category == "maintenance":
        when = _format_when(suggestion["date"])
        return f"🤔 להוסיף פריט תחזוקת בית: *{title}*{when}?\nענו \"כן\" לאישור או \"לא\" לביטול."

    # task (ברירת מחדל)
    when = _format_when(suggestion["date"]) if suggestion.get("date") else ""
    who = f" (ל{suggestion['assigned_name']})" if suggestion.get("assigned_name") else ""
    return f"🤔 ליצור משימה: *{title}*{when}{who}?\nענו \"כן\" לאישור או \"לא\" לביטול."


def _create_record_from_suggestion(suggestion: dict, chat_id: str):
    category = suggestion.get("category", "task")
    if category == "event":
        _create_event_from_suggestion(suggestion, chat_id)
    elif category == "payment":
        _create_payment_from_suggestion(suggestion, chat_id)
    elif category == "maintenance":
        _create_maintenance_from_suggestion(suggestion, chat_id)
    else:
        _create_task_from_suggestion(suggestion, chat_id)


def _create_task_from_suggestion(suggestion: dict, chat_id: str):
    db = SessionLocal()
    try:
        creator = db.query(User).filter(User.role == UserRole.PARENT).first()
        if not creator:
            logger.error("Telegram task creation: לא נמצא משתמש הורה לשיוך created_by — המשימה לא נוצרה")
            send_message_sync("⚠️ לא הצלחתי ליצור משימה — לא נמצא משתמש הורה רשום במערכת.", chat_id=chat_id)
            return

        assigned_to = None
        if suggestion.get("assigned_name"):
            match = db.query(User).filter(User.name == suggestion["assigned_name"]).first()
            if match:
                assigned_to = match.id

        due_date = _parse_dt(suggestion.get("date"))

        task = Task(
            title=suggestion["title"],
            created_by=creator.id,
            assigned_to=assigned_to,
            due_date=due_date,
            priority=TaskPriority.MEDIUM,
        )
        db.add(task)
        db.commit()

        assignee_name = None
        if assigned_to:
            assignee = db.query(User).filter(User.id == assigned_to).first()
            assignee_name = assignee.name if assignee else None

        who = f" ל{assignee_name}" if assignee_name else ""
        when = f" (עד {due_date.strftime('%d/%m %H:%M')})" if due_date else ""
        send_message_sync(f"✅ נוספה משימה{who}: *{suggestion['title']}*{when}", chat_id=chat_id)
    except Exception as e:
        logger.error(f"Telegram task creation נכשל: {e}")
        send_message_sync("⚠️ הייתה שגיאה ביצירת המשימה.", chat_id=chat_id)
    finally:
        db.close()


def _create_event_from_suggestion(suggestion: dict, chat_id: str):
    start_dt = _parse_dt(suggestion.get("date"))
    if not start_dt:
        send_message_sync("⚠️ לא הצלחתי להוסיף אירוע ליומן — לא זוהה תאריך.", chat_id=chat_id)
        return

    end_dt = _parse_dt(suggestion.get("end_date"))
    try:
        create_calendar_event(
            title=suggestion["title"],
            start=start_dt,
            end=end_dt,
            all_day=bool(suggestion.get("all_day")),
            location=suggestion.get("location"),
        )
        when = _format_when(suggestion["date"], suggestion.get("all_day"))
        where = f" ב{suggestion['location']}" if suggestion.get("location") else ""
        send_message_sync(f"📅 נוסף ליומן: *{suggestion['title']}*{when}{where}", chat_id=chat_id)
    except Exception as e:
        logger.error(f"Telegram event creation נכשל: {e}")
        send_message_sync("⚠️ הייתה שגיאה בהוספת האירוע ליומן.", chat_id=chat_id)


def _create_payment_from_suggestion(suggestion: dict, chat_id: str):
    due = _parse_dt(suggestion.get("date"))
    if not due:
        send_message_sync("⚠️ לא הצלחתי ליצור תזכורת תשלום — לא זוהה תאריך.", chat_id=chat_id)
        return

    recurrence = suggestion.get("recurrence") or "once"
    if recurrence not in _VALID_RECURRENCE:
        recurrence = "once"

    db = SessionLocal()
    try:
        payment = RecurringPayment(
            title=suggestion["title"],
            amount=suggestion.get("amount"),
            recurrence=recurrence,
            next_due_date=due.date(),
        )
        db.add(payment)
        db.commit()

        amount_str = f" ({suggestion['amount']:.0f} ש\"ח)" if suggestion.get("amount") else ""
        send_message_sync(
            f"💰 נוספה תזכורת תשלום: *{suggestion['title']}*{amount_str} עד {due.strftime('%d/%m')}",
            chat_id=chat_id,
        )
    except Exception as e:
        logger.error(f"Telegram payment creation נכשל: {e}")
        send_message_sync("⚠️ הייתה שגיאה ביצירת תזכורת התשלום.", chat_id=chat_id)
    finally:
        db.close()


def _create_maintenance_from_suggestion(suggestion: dict, chat_id: str):
    due = _parse_dt(suggestion.get("date"))
    if not due:
        send_message_sync("⚠️ לא הצלחתי ליצור פריט תחזוקה — לא זוהה תאריך.", chat_id=chat_id)
        return

    category = suggestion.get("maintenance_category") or "אחר"
    if category not in _VALID_MAINTENANCE_CATEGORIES:
        category = "אחר"

    db = SessionLocal()
    try:
        item = MaintenanceItem(
            name=suggestion["title"],
            category=category,
            next_due_date=due.date(),
        )
        db.add(item)
        db.commit()

        send_message_sync(
            f"🔧 נוסף פריט תחזוקת בית: *{suggestion['title']}* עד {due.strftime('%d/%m')}",
            chat_id=chat_id,
        )
    except Exception as e:
        logger.error(f"Telegram maintenance creation נכשל: {e}")
        send_message_sync("⚠️ הייתה שגיאה ביצירת פריט התחזוקה.", chat_id=chat_id)
    finally:
        db.close()

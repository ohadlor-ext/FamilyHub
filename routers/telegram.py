"""
Telegram → משימה: כיוון הפוך מ-services/telegram_bot.py (שזה רק יוצא/דחיפה).
כאן נכנסות הודעות שבני המשפחה שולחים *לתוך* הקבוצה, ו-AI (Claude) מחליט אם
הן בעצם משימה שצריך לשמור באפליקציה, מחלץ כותרת/תאריך/שיוך, ויוצר Task בהתאם.

זרימה:
1. Telegram שולח כל הודעה חדשה בקבוצה ל-POST /telegram/webhook (לאחר שמגדירים
   setWebhook חד-פעמי מול ה-API של טלגרם — ראו הוראות בהודעת הקומיט).
2. מאמתים שההודעה הגיעה מה-chat_id המוכר (TELEGRAM_FAMILY_CHAT_ID) ומה-secret
   token הנכון (TELEGRAM_WEBHOOK_SECRET, אם הוגדר) — כדי שלא כל גורם מהאינטרנט
   שמוצא את כתובת ה-webhook יוכל ליצור משימות.
3. אם יש הצעת משימה שמחכה לאישור מהודעה קודמת באותו chat — בודקים אם ההודעה
   הנוכחית היא תשובת כן/לא לה. אם לא, ההצעה הקודמת מתיישנת ומטופלת כהודעה רגילה.
4. קוראים ל-Claude (services/claude_ai.parse_telegram_task) לסנן/לחלץ. אם לא
   משימה — לא מגיבים בכלל (כדי לא להציף את קבוצת המשפחה). אם משימה בביטחון
   גבוה — נוצרת אוטומטית. אם ביטחון בינוני/נמוך — שולחים שאלת אישור ושומרים
   את ההצעה בזיכרון עד לתשובה.

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
from services.telegram_bot import send_message_sync
from services.claude_ai import parse_telegram_task

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

FAMILY_CHAT_ID = os.getenv("TELEGRAM_FAMILY_CHAT_ID")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

_CONFIRM_WORDS = {"כן", "אישור", "מאשר", "מאשרת", "yes", "y", "ok", "אוקיי", "👍", "✅"}
_CANCEL_WORDS = {"לא", "ביטול", "בטל", "no", "n", "cancel", "👎"}

# הצעת משימה שמחכה לאישור, לפי chat_id: {"title": str, "due_date": str|None, "assigned_name": str|None}
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
        return {"ok": True}  # סטיקרים/תמונות/וכו' — לא רלוונטי לפיצ'ר הזה

    chat_id = str(message["chat"]["id"])
    text = message["text"].strip()
    sender = message.get("from") or {}
    sender_name = sender.get("first_name") or sender.get("username") or "מישהו מהמשפחה"

    if FAMILY_CHAT_ID and chat_id != str(FAMILY_CHAT_ID):
        logger.warning(f"Telegram webhook: הודעה מ-chat_id לא מוכר ({chat_id}) — נדחתה")
        return {"ok": True}

    # תשובה להצעת משימה קודמת שמחכה באותו צ'אט?
    pending = _pending.get(chat_id)
    if pending:
        normalized = text.strip().lower()
        if text in _CONFIRM_WORDS or normalized in _CONFIRM_WORDS:
            del _pending[chat_id]
            _create_task_from_suggestion(pending, chat_id)
            return {"ok": True}
        if text in _CANCEL_WORDS or normalized in _CANCEL_WORDS:
            del _pending[chat_id]
            send_message_sync("בסדר, לא נוספה משימה.", chat_id=chat_id)
            return {"ok": True}
        # לא תגובת כן/לא — ההצעה הקודמת התיישנה, ממשיכים לטפל בהודעה הזו מהתחלה
        del _pending[chat_id]

    db = SessionLocal()
    try:
        family_names = [u.name for u in db.query(User).filter(User.is_active == True).all()]
    finally:
        db.close()

    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    try:
        result = parse_telegram_task(text, family_member_names=family_names, sender_name=sender_name, now=now)
    except Exception as e:
        logger.error(f"Telegram webhook: parse_telegram_task נכשל: {e}")
        return {"ok": True}

    if not result.get("is_task"):
        return {"ok": True}  # לא משימה — בכוונה לא מגיבים, כדי לא להציף את הקבוצה

    suggestion = {
        "title": (result.get("title") or text).strip(),
        "due_date": result.get("due_date"),
        "assigned_name": result.get("assigned_name"),
    }

    if result.get("confidence") == "high":
        _create_task_from_suggestion(suggestion, chat_id)
    else:
        _pending[chat_id] = suggestion
        when = f" עד {suggestion['due_date']}" if suggestion["due_date"] else ""
        who = f" (ל{suggestion['assigned_name']})" if suggestion["assigned_name"] else ""
        send_message_sync(
            f"🤔 ליצור משימה: *{suggestion['title']}*{when}{who}?\nענו \"כן\" לאישור או \"לא\" לביטול.",
            chat_id=chat_id,
        )

    return {"ok": True}


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

        due_date = None
        if suggestion.get("due_date"):
            try:
                due_date = datetime.fromisoformat(suggestion["due_date"]).replace(tzinfo=ZoneInfo("Asia/Jerusalem"))
            except ValueError:
                due_date = None

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

"""
iCloud Calendar (CalDAV) — שליפת אירועי לוח השנה המשפחתי

מחליף את Google Calendar: כל המשפחה רואה את לוח השנה היחיד של אבא ב-iCloud,
דרך חיבור CalDAV עם Apple ID app-specific password (שמור כ-ICLOUD_USERNAME /
ICLOUD_APP_PASSWORD ב-Railway, לא בקוד). בשונה מ-Google Calendar — אין כאן
טוקנים אישיים לכל משתמש, כולם קוראים מאותו חשבון iCloud אחד.

צורת הפלט (מבנה ה-dict לכל אירוע) זהה בכוונה ל-services/google_calendar.py
כך ש-routers/calendar.py והפרונט בלאבאבל לא צריכים שום שינוי.
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import caldav

logger = logging.getLogger(__name__)

ICLOUD_USERNAME = os.getenv("ICLOUD_USERNAME")
ICLOUD_APP_PASSWORD = os.getenv("ICLOUD_APP_PASSWORD")
# אופציונלי — אם יש כמה יומנים בחשבון ה-iCloud, לאיזה מהם ליצור אירועים חדשים (לפי שם מדויק).
# לא משפיע על קריאה (get_events_in_range קוראת מכולם) — רק על create_event. אם לא מוגדר,
# או שאין יומן בשם הזה, נכתב ליומן הראשון שמוחזר.
ICLOUD_CALENDAR_NAME = os.getenv("ICLOUD_CALENDAR_NAME")

# צבעי ברנד (לילך/סגול) — מחזור צבעים אם יש כמה יומנים בחשבון ה-iCloud
_CALENDAR_COLORS = ["#8B5CF6", "#A78BFA", "#F472B6", "#6D28D9"]


def _get_calendars() -> list:
    """מתחבר לשרת ה-CalDAV של iCloud ומחזיר את כל היומנים בחשבון"""
    if not ICLOUD_USERNAME or not ICLOUD_APP_PASSWORD:
        raise RuntimeError(
            "ICLOUD_USERNAME / ICLOUD_APP_PASSWORD לא מוגדרים ב-Railway — "
            "אי אפשר להתחבר ליומן ה-iCloud"
        )
    client = caldav.get_davclient(
        url="https://caldav.icloud.com/",
        username=ICLOUD_USERNAME,
        password=ICLOUD_APP_PASSWORD,
    )
    principal = client.principal()
    return principal.calendars()


def _event_to_dict(event, calendar_name: str, calendar_color: str) -> Optional[dict]:
    """מפענח אירוע CalDAV יחיד למבנה האחיד שהפרונט מצפה לו (כמו ב-Google Calendar)"""
    try:
        ical = event.get_icalendar_instance()
    except Exception:
        return None

    for component in ical.walk("VEVENT"):
        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        start_dt = dtstart.dt if dtstart else None
        end_dt = dtend.dt if dtend else None
        if start_dt is None:
            continue

        all_day = not isinstance(start_dt, datetime)
        description = component.get("description")
        location = component.get("location")

        return {
            "id": str(component.get("uid", "")),
            "title": str(component.get("summary", "ללא כותרת")),
            "description": str(description) if description else None,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat() if end_dt else None,
            "all_day": all_day,
            "calendar_name": calendar_name,
            "calendar_color": calendar_color,
            "location": str(location) if location else None,
        }
    return None


def get_events_in_range(start: datetime, end: datetime, max_results: int = 200) -> List[dict]:
    """אירועים בטווח תאריכים חופשי — משמש לתצוגות יומי/שבועי/חודשי"""
    events = []
    calendars = _get_calendars()

    for i, calendar in enumerate(calendars):
        try:
            cal_name = calendar.name or "יומן iCloud"
        except Exception:
            cal_name = "יומן iCloud"
        cal_color = _CALENDAR_COLORS[i % len(_CALENDAR_COLORS)]

        try:
            results = calendar.search(start=start, end=end, event=True, expand=True)
        except Exception:
            continue

        for event in results:
            parsed = _event_to_dict(event, cal_name, cal_color)
            if parsed:
                events.append(parsed)

    events.sort(key=lambda e: e["start"])
    return events[:max_results]


def get_upcoming_events(days_ahead: int = 7, max_results: int = 20) -> List[dict]:
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)
    return get_events_in_range(now, time_max, max_results=max_results)


def get_today_events() -> List[dict]:
    return get_upcoming_events(days_ahead=1)


def _get_target_calendar():
    """בוחר את היומן שאליו ייכתבו אירועים חדשים. אם הוגדר ICLOUD_CALENDAR_NAME — מחפש
    יומן בשם הזה (לדוגמה אם יש כמה יומנים בחשבון, כמו 'לוח שנה' + 'ימי הולדת' לקריאה-בלבד
    מאפל — לא נרצה לכתוב בטעות ליומן הלא נכון); אחרת לוקח את הראשון שמוחזר."""
    calendars = _get_calendars()
    if not calendars:
        raise RuntimeError("לא נמצא יומן ב-iCloud ליצירת אירוע")
    if ICLOUD_CALENDAR_NAME:
        for cal in calendars:
            try:
                if cal.name == ICLOUD_CALENDAR_NAME:
                    return cal
            except Exception:
                continue
        logger.warning(
            f"ICLOUD_CALENDAR_NAME='{ICLOUD_CALENDAR_NAME}' לא נמצא בין היומנים בחשבון — נכתב ליומן הראשון"
        )
    return calendars[0]


def list_calendars() -> List[dict]:
    """שמות כל היומנים בחשבון ה-iCloud, וסימון איזה מהם נבחר כיעד לכתיבה (כמו ב-_get_target_calendar).
    אנדפוינט אבחון בלבד (ר' routers/calendar.py GET /calendar/calendars) — שימושי כשcreate_event
    נכשל עם 403/AuthorizationError, כדי לזהות איזה יומן בחשבון הוא לא-כתיב (למשל יומן חגים/ימי
    הולדת/משותף לקריאה בלבד) ולהגדיר את השם המדויק של היומן הכתיב ב-ICLOUD_CALENDAR_NAME ב-Railway."""
    calendars = _get_calendars()
    names = []
    for cal in calendars:
        try:
            names.append(cal.name)
        except Exception:
            names.append(None)

    target_index = 0
    if ICLOUD_CALENDAR_NAME and ICLOUD_CALENDAR_NAME in names:
        target_index = names.index(ICLOUD_CALENDAR_NAME)

    return [{"name": name, "is_write_target": i == target_index} for i, name in enumerate(names)]


def create_event(
    title: str,
    start: datetime,
    end: Optional[datetime] = None,
    all_day: bool = False,
    location: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """יוצר אירוע חדש ביומן ה-iCloud (ר' _get_target_calendar לבחירת היומן).
    משמש ע"י routers/telegram.py כשהודעה בקבוצה מזוהה כאירוע ליומן (למשל "לרוני יש
    מסיבה ביום חמישי") — כך שהוא מסונכרן אוטומטית ליומן האפל המשפחתי, בלי שמישהו
    צריך להוסיף אותו ביד.
    start/end: datetime מודע-אזור-זמן (Asia/Jerusalem) ל-all_day=False, או כל datetime
    ל-all_day=True (רק התאריך נלקח). אם end לא מצוין: שעה אחת אחרי start (או יום
    שלם אחרי start.date() ב-all_day)."""
    calendar = _get_target_calendar()

    if all_day:
        dtstart = start.date() if isinstance(start, datetime) else start
        dtend = (end.date() if isinstance(end, datetime) else end) if end else dtstart + timedelta(days=1)
    else:
        dtstart = start
        dtend = end or (start + timedelta(hours=1))

    kwargs = {"summary": title, "dtstart": dtstart, "dtend": dtend}
    if location:
        kwargs["location"] = location
    if description:
        kwargs["description"] = description

    event = calendar.add_event(**kwargs)

    try:
        cal_name = calendar.name or "יומן iCloud"
    except Exception:
        cal_name = "יומן iCloud"

    return {
        "id": event.id,
        "title": title,
        "start": dtstart.isoformat(),
        "end": dtend.isoformat(),
        "all_day": all_day,
        "calendar_name": cal_name,
        "location": location,
    }

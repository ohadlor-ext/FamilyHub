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
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import caldav

ICLOUD_USERNAME = os.getenv("ICLOUD_USERNAME")
ICLOUD_APP_PASSWORD = os.getenv("ICLOUD_APP_PASSWORD")

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

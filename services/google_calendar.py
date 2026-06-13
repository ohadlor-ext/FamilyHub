"""
Google Calendar API — שליפת אירועים משפחתיים
"""
from datetime import datetime, timedelta, timezone
from typing import List
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_calendar_service(access_token: str, refresh_token: str = None):
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("calendar", "v3", credentials=creds)


def get_upcoming_events(
    access_token: str,
    refresh_token: str = None,
    days_ahead: int = 7,
    max_results: int = 20,
) -> List[dict]:
    service = get_calendar_service(access_token, refresh_token)
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)

    events = []
    calendars = service.calendarList().list().execute().get("items", [])

    for calendar in calendars:
        cal_id = calendar["id"]
        result = service.events().list(
            calendarId=cal_id,
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        for event in result.get("items", []):
            start = event.get("start", {})
            events.append({
                "id": event.get("id"),
                "title": event.get("summary", "ללא כותרת"),
                "description": event.get("description"),
                "start": start.get("dateTime") or start.get("date"),
                "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
                "all_day": "date" in start and "dateTime" not in start,
                "calendar_name": calendar.get("summary"),
                "calendar_color": calendar.get("backgroundColor", "#4285F4"),
                "location": event.get("location"),
            })

    events.sort(key=lambda e: e["start"])
    return events[:max_results]


def get_today_events(access_token: str, refresh_token: str = None) -> List[dict]:
    return get_upcoming_events(access_token, refresh_token, days_ahead=1)

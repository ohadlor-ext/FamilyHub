from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from routers.auth import get_current_user_dep
from models.user import User
from services.icloud_calendar import get_upcoming_events, get_today_events, get_events_in_range

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
def list_events(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user_dep),
):
    """אירועים קרובים מיומן ה-iCloud המשפחתי"""
    events = get_upcoming_events(days_ahead=days)
    return {"events": events, "count": len(events)}


@router.get("/today")
def today_events(current_user: User = Depends(get_current_user_dep)):
    """אירועי היום בלבד — לדשבורד הטאבלט"""
    events = get_today_events()
    return {"events": events, "count": len(events)}


@router.get("/range")
def events_in_range(
    start: str = Query(..., description="תאריך התחלה, פורמט YYYY-MM-DD"),
    end: str = Query(..., description="תאריך סיום (כולל), פורמט YYYY-MM-DD"),
    current_user: User = Depends(get_current_user_dep),
):
    """אירועים בטווח תאריכים חופשי — לתצוגות יומי / שבועי / חודשי בדשבורד"""
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="פורמט תאריך לא תקין — יש להשתמש ב-YYYY-MM-DD")

    events = get_events_in_range(start_dt, end_dt)
    return {"events": events, "count": len(events), "start": start, "end": end}

from fastapi import APIRouter, Depends, Query
from routers.auth import get_current_user_dep
from models.user import User
from services.google_calendar import get_upcoming_events, get_today_events

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
def list_events(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user_dep),
):
    """אירועים קרובים מהלוח השנה של המשתמש"""
    events = get_upcoming_events(
        access_token=current_user.google_access_token,
        refresh_token=current_user.google_refresh_token,
        days_ahead=days,
    )
    return {"events": events, "count": len(events)}


@router.get("/today")
def today_events(current_user: User = Depends(get_current_user_dep)):
    """אירועי היום בלבד — לדשבורד הטאבלט"""
    events = get_today_events(
        access_token=current_user.google_access_token,
        refresh_token=current_user.google_refresh_token,
    )
    return {"events": events, "count": len(events)}

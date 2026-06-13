from fastapi import APIRouter
from services.openweather import get_current_weather, get_forecast

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current")
async def current_weather():
    """מזג אוויר נוכחי — לא דורש אימות"""
    return await get_current_weather()


@router.get("/forecast")
async def weather_forecast():
    """תחזית ל-5 ימים"""
    return {"forecast": await get_forecast()}

"""
OpenWeatherMap API — מזג אוויר אשדוד / בת ים
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEATHER_API_KEY")
CITY = os.getenv("WEATHER_CITY", "Ashdod")
COUNTRY = os.getenv("WEATHER_COUNTRY", "IL")
LANG = os.getenv("WEATHER_LANG", "he")
BASE_URL = "https://api.openweathermap.org/data/2.5"

WEATHER_ICONS = {
    "01d": "☀️", "01n": "🌙",
    "02d": "⛅", "02n": "🌙☁️",
    "03d": "☁️", "03n": "☁️",
    "04d": "☁️", "04n": "☁️",
    "09d": "🌧️", "09n": "🌧️",
    "10d": "🌦️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️",
    "13d": "❄️", "13n": "❄️",
    "50d": "🌫️", "50n": "🌫️",
}


async def get_current_weather() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/weather",
            params={
                "q": f"{CITY},{COUNTRY}",
                "appid": API_KEY,
                "units": "metric",
                "lang": LANG,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    icon_code = data["weather"][0]["icon"]
    return {
        "city": "בת ים / אשדוד",
        "temp": round(data["main"]["temp"]),
        "feels_like": round(data["main"]["feels_like"]),
        "temp_min": round(data["main"]["temp_min"]),
        "temp_max": round(data["main"]["temp_max"]),
        "humidity": data["main"]["humidity"],
        "description": data["weather"][0]["description"],
        "icon": WEATHER_ICONS.get(icon_code, "🌡️"),
        "icon_code": icon_code,
        "wind_speed": round(data["wind"]["speed"] * 3.6),
    }


async def get_forecast() -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/forecast",
            params={
                "q": f"{CITY},{COUNTRY}",
                "appid": API_KEY,
                "units": "metric",
                "lang": LANG,
                "cnt": 40,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    daily = {}
    for item in data["list"]:
        date = item["dt_txt"][:10]
        if date not in daily:
            icon_code = item["weather"][0]["icon"]
            daily[date] = {
                "date": date,
                "temp_max": item["main"]["temp_max"],
                "temp_min": item["main"]["temp_min"],
                "description": item["weather"][0]["description"],
                "icon": WEATHER_ICONS.get(icon_code, "🌡️"),
            }
        else:
            daily[date]["temp_max"] = max(daily[date]["temp_max"], item["main"]["temp_max"])
            daily[date]["temp_min"] = min(daily[date]["temp_min"], item["main"]["temp_min"])

    return [
        {**v, "temp_max": round(v["temp_max"]), "temp_min": round(v["temp_min"])}
        for v in list(daily.values())[:5]
    ]

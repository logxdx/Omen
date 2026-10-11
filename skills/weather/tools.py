"""Weather skill: current conditions + forecast from wttr.in."""

from __future__ import annotations

from omen.core.tools import ToolResult, tool

from .weather import fetch_weather_json


@tool
def get_weather(city: str) -> ToolResult:
    """Current weather and a 3-day forecast for a city.

    Args:
        city: City name, e.g. "Paris" or "New York".
    """
    data = fetch_weather_json(city)
    now = data["current_condition"][0]
    area = (data.get("nearest_area") or [{}])[0]
    place = ", ".join(
        part[0]["value"] for part in (area.get("areaName"), area.get("country")) if part
    ) or city
    condition = now["weatherDesc"][0]["value"].strip()
    forecast = [
        {"date": d["date"], "min_c": int(d["mintempC"]), "max_c": int(d["maxtempC"])}
        for d in data.get("weather", [])[:3]
    ]
    days = "; ".join(f"{f['date']}: {f['min_c']}-{f['max_c']}°C" for f in forecast)
    content = (
        f"{place}: {now['temp_C']}°C (feels like {now['FeelsLikeC']}°C), {condition}, "
        f"humidity {now['humidity']}%, wind {now['windspeedKmph']} km/h.\nForecast: {days}"
    )
    return ToolResult(
        content,
        details={
            "type": "weather",
            "place": place,
            "temp_c": int(now["temp_C"]),
            "feels_like_c": int(now["FeelsLikeC"]),
            "condition": condition,
            "humidity": int(now["humidity"]),
            "wind_kmph": int(now["windspeedKmph"]),
            "observed": now.get("localObsDateTime"),
            "forecast": forecast,
        },
    )


TOOLS = [get_weather]

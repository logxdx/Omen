import json
import requests


# Get current weather
def get_weather(city: str) -> str:
    """
    Get the current weather for a city

    Args:
        city: The city to get the weather for

    Returns:
        str: Formatted weather information or error message
    """
    if not city or not isinstance(city, str):
        error_msg = "Invalid city name provided"
        return error_msg

    try:
        city_encoded = city.replace(" ", "+")
        base_url = f"http://wttr.in/{city_encoded}?format=j1"

        response = requests.get(base_url, timeout=5)
        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching weather data: {str(e)}"
        return f"Error: Could not retrieve weather data. {str(e)}"
    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Error parsing weather data: {str(e)}"
        return "Error: Could not parse weather data."

    current_stats = {}
    current_condition = data["current_condition"][0]
    weather = data["weather"]

    # current conditions
    date = current_condition["localObsDateTime"]
    humidity = current_condition["humidity"]
    precip = current_condition["precipMM"]
    pressure = current_condition["pressure"]
    temp = current_condition["temp_C"]
    uvindex = current_condition["uvIndex"]
    visibility = current_condition["visibility"]
    weather_desc = current_condition["weatherDesc"][0]["value"]
    wind_speed = current_condition["windspeedKmph"]

    # weather forecast for current day
    current_stats[date] = {
        "weather": weather_desc,
        "temperature": temp,
        "visibility": visibility,
        "humidity": humidity,
        "precipitation": precip,
        "wind_speed": wind_speed,
        "pressure": pressure,
        "uvindex": uvindex,
    }

    stats = {}
    # weather forecast for coming days
    for day in weather:
        date = day["date"]
        max_temp = day["maxtempC"]
        min_temp = day["mintempC"]
        avg_temp = day["avgtempC"]
        uv = day["uvIndex"]
        stats[date] = {
            "max_temp": max_temp,
            "min_temp": min_temp,
            "avg_temp": avg_temp,
            "uvindex": uv,
        }

    lines: list[str] = []
    lines.append(f"Current weather in {city}:")
    for obs_time, data_point in current_stats.items():
        lines.append(f"- Observed: {obs_time}")
        lines.append(f"  - Weather: {data_point.get('weather', 'N/A')}")
        lines.append(f"  - Temperature: {data_point.get('temperature', 'N/A')}°C")
        lines.append(f"  - Humidity: {data_point.get('humidity', 'N/A')}%")
        lines.append(f"  - Precipitation: {data_point.get('precipitation', 'N/A')} mm")
        lines.append(f"  - Wind: {data_point.get('wind_speed', 'N/A')} km/h")
        lines.append(f"  - Visibility: {data_point.get('visibility', 'N/A')} km")
        lines.append(f"  - Pressure: {data_point.get('pressure', 'N/A')} hPa")
        lines.append(f"  - UV Index: {data_point.get('uvindex', 'N/A')}")
    lines.append("")
    lines.append("Weather forecast for the coming days:")
    for date in sorted(stats.keys()):
        d = stats[date]
        lines.append(
            f"- {date}: Low {d.get('min_temp', 'N/A')}°C, "
            f"High {d.get('max_temp', 'N/A')}°C, "
            f"Avg {d.get('avg_temp', 'N/A')}°C, UV {d.get('uvindex', 'N/A')}"
        )

    output = "\n".join(lines)

    return output

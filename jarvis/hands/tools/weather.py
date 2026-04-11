"""Weather tool using wttr.in free API."""
import logging
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)

async def get_weather(location: str = "", **kwargs) -> ToolResult:
    """Get current weather and forecast for a location."""
    import aiohttp

    url = f"https://wttr.in/{location}?format=j1" if location else "https://wttr.in/?format=j1"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return ToolResult(success=False, error=f"Weather API returned {resp.status}")
                data = await resp.json()

                current = data.get("current_condition", [{}])[0]
                area = data.get("nearest_area", [{}])[0]

                city = area.get("areaName", [{}])[0].get("value", "Unknown")
                country = area.get("country", [{}])[0].get("value", "")
                temp_f = current.get("temp_F", "?")
                temp_c = current.get("temp_C", "?")
                desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
                humidity = current.get("humidity", "?")
                feels_like_f = current.get("FeelsLikeF", "?")
                wind_mph = current.get("windspeedMiles", "?")

                # Get today's forecast
                forecast = data.get("weather", [{}])[0]
                max_f = forecast.get("maxtempF", "?")
                min_f = forecast.get("mintempF", "?")

                weather_data = {
                    "location": f"{city}, {country}",
                    "temperature_f": temp_f,
                    "temperature_c": temp_c,
                    "feels_like_f": feels_like_f,
                    "condition": desc,
                    "humidity": f"{humidity}%",
                    "wind_mph": wind_mph,
                    "high_f": max_f,
                    "low_f": min_f,
                }

                display = (
                    f"Currently {temp_f}°F ({temp_c}°C) and {desc.lower()} in {city}. "
                    f"Feels like {feels_like_f}°F. High of {max_f}°F, low of {min_f}°F. "
                    f"Humidity {humidity}%, wind {wind_mph} mph."
                )

                return ToolResult(success=True, data=weather_data, display_text=display)
    except Exception as e:
        logger.exception("Weather fetch failed")
        return ToolResult(success=False, error=str(e), display_text="Failed to get weather data.")


def register(executor, platform, config):
    executor.register("get_weather", get_weather)

"""
Weather Agent — Singapore real-time weather from data.gov.sg
Tools cover all the major NEA endpoints.
No HITL needed — all weather reads are safe and passive.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import datetime
import logging
import requests

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from utils.main_utils import llm_model
from logic.graph.state import saver

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
today = datetime.datetime.now().strftime("%Y-%m-%d")

OPEN_DATA_API_KEY = os.getenv("OPEN_DATA_API_KEY")

# ==========================================
# API Endpoints
# ==========================================
BASE = "https://api-open.data.gov.sg/v2/real-time/api"
ENDPOINTS = {
    "two_hour_forecast":      f"{BASE}/two-hr-forecast",
    "twenty_four_hr_forecast":f"{BASE}/twenty-four-hr-forecast",
    "four_day_outlook":       f"{BASE}/four-day-outlook",
    "air_temperature":        f"{BASE}/air-temperature",
    "relative_humidity":      f"{BASE}/relative-humidity",
    "rainfall":               f"{BASE}/rainfall",
    "wind_speed":             f"{BASE}/wind-speed",
    "uv_index":               f"{BASE}/uv-index",
    "psi":                    f"{BASE}/psi",
}

# Open-Meteo (worldwide, no API key needed)
GEO_API     = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

def _get(url: str) -> dict:
    """Make an authenticated GET request to the data.gov.sg API."""
    headers = {}
    if OPEN_DATA_API_KEY:
        headers["X-Api-Key"] = OPEN_DATA_API_KEY
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


# Key representative stations per region (avoids dumping all 50+ stations)
REGION_STATIONS = {
    "North":   ["S107", "S111", "S117"],  # Woodlands, Sembawang, Yishun
    "South":   ["S60",  "S104", "S116"],  # Sentosa, Buona Vista, Tanjong Pagar
    "East":    ["S24",  "S43",  "S50"],   # Changi, Pasir Ris, Tampines
    "West":    ["S44",  "S106", "S121"],  # Jurong, Clementi, Tuas
    "Central": ["S109", "S115", "S116"],  # Ang Mo Kio, Toa Payoh, Novena
}


def _aggregate(readings: list, unit: str) -> str:
    """Return min/avg/max summary from a list of numeric readings."""
    values = [r["value"] for r in readings if isinstance(r.get("value"), (int, float))]
    if not values:
        return "No data"
    return f"min {min(values):.1f}{unit} / avg {sum(values)/len(values):.1f}{unit} / max {max(values):.1f}{unit}"


# ==========================================
# Tools
# ==========================================

@tool
def get_two_hour_forecast(area: str = "") -> str:
    """
    Get the 2-hour weather forecast for Singapore areas.
    Optionally filter by 'area' name (e.g. 'Tampines', 'Orchard', 'Woodlands').
    If no area is given, returns forecasts for all areas.
    """
    logger.info("Fetching 2-hour weather forecast")
    data = _get(ENDPOINTS["two_hour_forecast"])

    items = data.get("data", {}).get("items", [])
    if not items:
        return "No 2-hour forecast data available right now."

    latest = items[0]
    valid = latest.get("valid_period", {}).get("text", "")
    forecasts = latest.get("forecasts", [])

    if area:
        forecasts = [f for f in forecasts if area.lower() in f["area"].lower()]
        if not forecasts:
            return f"No forecast found for area: '{area}'. Try a different area name."

    lines = [f"🌦️ 2-Hour Forecast (Valid: {valid})\n"]
    for f in forecasts:
        lines.append(f"  📍 {f['area']}: {f['forecast']}")
    return "\n".join(lines)


@tool
def get_temperature(area: str = "") -> str:
    """
    Get air temperature readings.
    If 'area' is given (e.g. 'Woodlands', 'Tampines'), return specific station readings.
    If empty, return a concise regional summary (North/South/East/West/Central) instead of all stations.
    """
    logger.info(f"Fetching air temperature (area='{area}')")
    data = _get(ENDPOINTS["air_temperature"])

    readings_data = data.get("data", {}).get("readings", [])
    stations = {s["id"]: s["name"] for s in data.get("data", {}).get("stations", [])}

    if not readings_data:
        return "No temperature data available right now."

    all_readings = readings_data[0].get("data", [])
    timestamp = readings_data[0].get("timestamp", "")

    if area:
        # Specific area — list individual stations
        filtered = [r for r in all_readings if area.lower() in stations.get(r["stationId"], "").lower()]
        if not filtered:
            return f"No temperature station found near '{area}'."
        lines = [f"🌡️ Temperature near {area} (as of {timestamp})\n"]
        for r in filtered:
            lines.append(f"  📍 {stations.get(r['stationId'], r['stationId'])}: {r['value']}°C")
        return "\n".join(lines)
    else:
        # No area — return regional summary
        lines = [f"🌡️ Temperature Summary (as of {timestamp})\n"]
        for region, ids in REGION_STATIONS.items():
            region_readings = [r for r in all_readings if r["stationId"] in ids]
            lines.append(f"  {region}: {_aggregate(region_readings, '°C')}")
        return "\n".join(lines)


@tool
def get_humidity(area: str = "") -> str:
    """
    Get relative humidity readings.
    If 'area' is given, return specific station readings.
    If empty, return a concise regional summary.
    """
    logger.info(f"Fetching humidity (area='{area}')")
    data = _get(ENDPOINTS["relative_humidity"])

    readings_data = data.get("data", {}).get("readings", [])
    stations = {s["id"]: s["name"] for s in data.get("data", {}).get("stations", [])}

    if not readings_data:
        return "No humidity data available right now."

    all_readings = readings_data[0].get("data", [])
    timestamp = readings_data[0].get("timestamp", "")

    if area:
        filtered = [r for r in all_readings if area.lower() in stations.get(r["stationId"], "").lower()]
        if not filtered:
            return f"No humidity station found near '{area}'."
        lines = [f"💧 Humidity near {area} (as of {timestamp})\n"]
        for r in filtered:
            lines.append(f"  📍 {stations.get(r['stationId'], r['stationId'])}: {r['value']}%")
        return "\n".join(lines)
    else:
        lines = [f"💧 Humidity Summary (as of {timestamp})\n"]
        for region, ids in REGION_STATIONS.items():
            region_readings = [r for r in all_readings if r["stationId"] in ids]
            lines.append(f"  {region}: {_aggregate(region_readings, '%')}")
        return "\n".join(lines)


@tool
def get_wind_speed(area: str = "") -> str:
    """
    Get wind speed readings (km/h).
    If 'area' is given, return specific station readings.
    If empty, return a concise regional summary.
    """
    logger.info(f"Fetching wind speed (area='{area}')")
    data = _get(ENDPOINTS["wind_speed"])

    readings_data = data.get("data", {}).get("readings", [])
    stations = {s["id"]: s["name"] for s in data.get("data", {}).get("stations", [])}

    if not readings_data:
        return "No wind speed data available right now."

    all_readings = readings_data[0].get("data", [])
    timestamp = readings_data[0].get("timestamp", "")

    if area:
        filtered = [r for r in all_readings if area.lower() in stations.get(r["stationId"], "").lower()]
        if not filtered:
            return f"No wind speed station found near '{area}'."
        lines = [f"💨 Wind Speed near {area} (as of {timestamp})\n"]
        for r in filtered:
            lines.append(f"  📍 {stations.get(r['stationId'], r['stationId'])}: {r['value']} km/h")
        return "\n".join(lines)
    else:
        lines = [f"💨 Wind Speed Summary (as of {timestamp})\n"]
        for region, ids in REGION_STATIONS.items():
            region_readings = [r for r in all_readings if r["stationId"] in ids]
            lines.append(f"  {region}: {_aggregate(region_readings, ' km/h')}")
        return "\n".join(lines)


@tool
def get_rainfall(area: str = "") -> str:
    """
    Get rainfall readings (mm).
    If 'area' is given, return specific station readings.
    If empty, return a concise regional summary.
    """
    logger.info(f"Fetching rainfall (area='{area}')")
    data = _get(ENDPOINTS["rainfall"])

    readings_data = data.get("data", {}).get("readings", [])
    stations = {s["id"]: s["name"] for s in data.get("data", {}).get("stations", [])}

    if not readings_data:
        return "No rainfall data available right now."

    all_readings = readings_data[0].get("data", [])
    timestamp = readings_data[0].get("timestamp", "")

    if area:
        filtered = [r for r in all_readings if area.lower() in stations.get(r["stationId"], "").lower()]
        if not filtered:
            return f"No rainfall station found near '{area}'."
        lines = [f"🌧️ Rainfall near {area} (as of {timestamp})\n"]
        for r in filtered:
            lines.append(f"  📍 {stations.get(r['stationId'], r['stationId'])}: {r['value']} mm")
        return "\n".join(lines)
    else:
        lines = [f"🌧️ Rainfall Summary (as of {timestamp})\n"]
        for region, ids in REGION_STATIONS.items():
            region_readings = [r for r in all_readings if r["stationId"] in ids]
            lines.append(f"  {region}: {_aggregate(region_readings, ' mm')}")
        return "\n".join(lines)


@tool
def get_uv_index() -> str:
    """Get the current UV index in Singapore."""
    logger.info("Fetching UV index")
    data = _get(ENDPOINTS["uv_index"])

    records = data.get("data", {}).get("records", [])
    if not records:
        return "No UV index data available right now."

    latest = records[0]
    timestamp = latest.get("timestamp", "")
    uv_val = latest.get("index", [{}])
    value = uv_val[0].get("value", "N/A") if uv_val else "N/A"

    level = "Low"
    if isinstance(value, (int, float)):
        if value >= 11:   level = "Extreme"
        elif value >= 8:  level = "Very High"
        elif value >= 6:  level = "High"
        elif value >= 3:  level = "Moderate"

    return f"☀️ UV Index (as of {timestamp}): {value} ({level})"


@tool
def get_psi() -> str:
    """Get the current Pollutant Standards Index (PSI) and air quality in Singapore."""
    logger.info("Fetching PSI")
    data = _get(ENDPOINTS["psi"])

    items = data.get("data", {}).get("items", [])
    if not items:
        return "No PSI data available right now."

    latest = items[0]
    timestamp = latest.get("timestamp", "")
    readings = latest.get("readings", {})
    
    psi_24h = readings.get("psi_twenty_four_hourly", {})
    pm25 = readings.get("pm25_twenty_four_hourly", {})

    lines = [f"🌫️ Air Quality PSI (as of {timestamp})\n"]
    for region, val in psi_24h.items():
        pm = pm25.get(region, "N/A")
        lines.append(f"  📍 {region.capitalize()}: PSI {val} | PM2.5: {pm}")
    return "\n".join(lines)


@tool
def get_four_day_outlook() -> str:
    """Get the 4-day weather outlook for Singapore."""
    logger.info("Fetching 4-day weather outlook")
    data = _get(ENDPOINTS["four_day_outlook"])

    records = data.get("data", {}).get("records", [])
    if not records:
        return "No 4-day forecast available right now."

    lines = ["📅 4-Day Weather Outlook for Singapore\n"]
    for record in records:
        for forecast in record.get("forecasts", []):
            date = forecast.get("date", "")
            summary = forecast.get("forecast", {}).get("summary", "")
            temp = forecast.get("temperature", {})
            low = temp.get("low", "?")
            high = temp.get("high", "?")
            rain = forecast.get("relative_humidity", {})
            lines.append(f"  📅 {date}: {summary} | 🌡️ {low}–{high}°C")
    return "\n".join(lines)

@tool
def get_worldwide_weather(city: str) -> str:
    """
    Get the current weather for ANY city in the world.
    'city' can be a city name or country (e.g. 'Tokyo', 'London', 'Germany', 'New York').
    Uses the Open-Meteo API — no API key required.
    WMO weather code meanings are included in the output.
    """
    logger.info(f"Fetching worldwide weather for city: '{city}'")

    # Step 1: Geocode the city name to get coordinates
    geo_resp = requests.get(GEO_API, params={"name": city, "count": 1}, timeout=10)
    geo_resp.raise_for_status()
    geo_data = geo_resp.json()

    results = geo_data.get("results", [])
    if not results:
        return f"Could not find the location: '{city}'. Try a different city or country name."

    location = results[0]
    name      = location.get("name", city)
    country   = location.get("country", "")
    lat       = location.get("latitude")
    lon       = location.get("longitude")
    timezone  = location.get("timezone", "UTC")
    logger.info(f"Resolved '{city}' → {name}, {country} ({lat}, {lon})")

    # Step 2: Fetch current weather using coordinates
    forecast_resp = requests.get(
        FORECAST_API,
        params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m",
            "forecast_days": 1,
            "timezone": timezone,
        },
        timeout=10
    )
    forecast_resp.raise_for_status()
    forecast_data = forecast_resp.json()

    cw = forecast_data.get("current_weather", {})
    temp       = cw.get("temperature", "N/A")
    wind_speed = cw.get("windspeed", "N/A")
    wind_dir   = cw.get("winddirection", "N/A")
    wmo_code   = cw.get("weathercode", -1)
    time_str   = cw.get("time", "")

    # WMO weather code to human-readable description
    WMO_CODES = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
    }
    condition = WMO_CODES.get(wmo_code, f"Weather code {wmo_code}")

    return (
        f"🌍 Current Weather in {name}, {country}\n"
        f"   🕐 Time: {time_str} ({timezone})\n"
        f"   🌡️ Temperature: {temp}°C\n"
        f"   🌤️ Condition: {condition}\n"
        f"   💨 Wind: {wind_speed} km/h from {wind_dir}°\n"
    )

weather_tools = [
    get_two_hour_forecast,
    get_temperature,
    get_humidity,
    get_wind_speed,
    get_rainfall,
    get_uv_index,
    get_psi,
    get_four_day_outlook,
    get_worldwide_weather,
]

weather_system_prompt = f"""You are a helpful Singapore / Worldwide weather assistant powered by real-time NEA data.
Today's date is {today}.

Available tools:
- get_two_hour_forecast: 2-hour forecast by area (e.g. Tampines, Woodlands)
- get_temperature: Real-time temperature readings by station/area
- get_humidity: Real-time humidity readings
- get_wind_speed: Real-time wind speed readings
- get_rainfall: Real-time rainfall readings
- get_uv_index: Current UV index and risk level
- get_psi: Air quality / Pollutant Standards Index
- get_four_day_outlook: 4-day weather forecast
- get_worldwide_weather: Current weather for ANY city in the world

Singapore geography mapping:
- North: Woodlands, Yishun, Sembawang, Admiralty
- South: Sentosa, HarbourFront, Marina Bay
- East: Tampines, Pasir Ris, Bedok, Changi
- West: Jurong, Bukit Batok, Clementi
- Central: Orchard, Toa Payoh, Bishan, Novena, Ang Mo Kio

Rules:
1. Determine location scope:
   - If the location is in Singapore → use Singapore tools
   - If the location is outside Singapore → use get_worldwide_weather
   - If unclear → ask a clarification question

2. Determine the user's location:
   - If explicitly provided → use it
   - If vague (e.g. "near me"):
       - Assume Singapore Central ONLY if user context is Singapore
       - Otherwise ask for clarification

3. Tool selection:
   - Rain / "will it rain" → get_two_hour_forecast + get_rainfall (Singapore only)
   - Heat / temperature → get_temperature + get_humidity
   - Wind → get_wind_speed
   - UV → get_uv_index
   - Air quality → get_psi
   - Future weather → get_four_day_outlook

4. Worldwide queries:
   - Always use get_worldwide_weather
   - Do NOT use Singapore-specific tools

5. Singapore queries:
   - Always map user location to the closest Singapore area
   - Pass the mapped area into the tool

6. Combine tools when needed:
   Example:
   - "Weather now" → temperature + humidity + rainfall + forecast

7. Response style:
   - Start with a direct answer
   - Then provide a short breakdown
   - Keep it concise and easy to read

8. Never hallucinate weather data. Always rely on tool outputs.

9. No HITL required — all tools are safe read operations.
"""

# No HumanInTheLoopMiddleware — weather reads are always safe
weather_react_agent = create_agent(
    model=llm_model,
    system_prompt=weather_system_prompt,
    tools=weather_tools,
    checkpointer=saver,
)

# ==========================================
# LangGraph Node Wrapper
# ==========================================

def weather_worker_node(state: dict, config: RunnableConfig) -> dict:
    """LangGraph node that runs the weather agent."""
    logger.info("⛅ Weather worker node invoked.")
    response = weather_react_agent.invoke(
        {"messages": state["messages"]},
        config=config
    )
    logger.info("⛅ Weather worker node finished.")
    messages = response.get("messages", []) if isinstance(response, dict) else []
    return {"messages": messages}


# ==========================================
# Local Test
# ==========================================

if __name__ == "__main__":
    print("\n⛅ Weather Agent Chat (type 'quit' to exit)\n")
    config: RunnableConfig = {"configurable": {"thread_id": "weather_test_1"}}
    user_input = input("You: ").strip()

    while True:
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        response = weather_react_agent.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )
        if response and "messages" in response:
            print(f"\n⛅ Agent: {response['messages'][-1].content}\n")

        user_input = input("You: ").strip()


"""
User: "What's the weather in Tokyo?"
          ↓
Step 1: GET geocoding-api.open-meteo.com/v1/search?name=Tokyo&count=1
        → Returns: lat=35.689, lon=139.692, timezone="Asia/Tokyo"
          ↓
Step 2: GET api.open-meteo.com/v1/forecast?latitude=35.689&longitude=139.692&current_weather=true
        → Returns: temp, wind speed, WMO weather code
          ↓
Output:
🌍 Current Weather in Tokyo, Japan
   🕐 Time: 2026-04-02T01:00 (Asia/Tokyo)
   🌡️ Temperature: 12.3°C
   🌤️ Condition: Partly cloudy
   💨 Wind: 14.2 km/h from 180°



"""
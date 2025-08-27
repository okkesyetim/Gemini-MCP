from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import logging

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
)


# Initialize the FastMCP server
mcp = FastMCP("weather_tools")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "gemini-mcp-client/1.0 (contact@example.com)"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Makes a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    logging.info(f"-> Making external API request to: {url}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            response.raise_for_status()
            logging.info(f"<- Received successful API response (Status: {response.status_code})")
            return response.json()
        except httpx.RequestError as e:
            logging.error(f"!! API request failed: {e}")
            return None


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Gets active weather alerts for a US state.
    Args:
        state: Two-letter US state code (e.g., CA, NY)
    """
    logging.info(f"Executing tool 'get_alerts' with state='{state}'")
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)
    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."
    if not data["features"]:
        return f"No active alerts for the state: {state}."

    alerts = [f"Event: {f['properties'].get('event', 'N/A')}, Area: {f['properties'].get('areaDesc', 'N/A')}" for f in
              data["features"]]
    return "\n---\n".join(alerts)


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Gets the weather forecast for a specific location.
    Args:
        latitude: The latitude of the location.
        longitude: The longitude of the location.
    """
    logging.info(f"Executing tool 'get_forecast' with lat={latitude}, lon={longitude}")
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)
    if not points_data or "properties" not in points_data:
        return "Unable to fetch location data to get forecast."

    forecast_url = points_data["properties"].get("forecast")
    if not forecast_url:
        return "Could not find a forecast URL for the given coordinates."

    forecast_data = await make_nws_request(forecast_url)
    if not forecast_data or "properties" not in forecast_data:
        return "Unable to fetch the detailed forecast."

    periods = forecast_data["properties"].get("periods", [])
    if not periods:
        return "No forecast periods found in the data."

    forecasts = [f"{p['name']}: {p['temperature']}°{p['temperatureUnit']}, {p['detailedForecast']}" for p in
                 periods[:5]]
    return "\n---\n".join(forecasts)


if __name__ == "__main__":
    mcp.run(transport='stdio')
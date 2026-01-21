"""
Gemini AI Property Analysis Service

Ported from PropIntel TypeScript implementation.
Uses Gemini 2.5 Flash with Google Search grounding for commercial real estate analysis.
"""

import os
import re
import json
import httpx
from typing import Optional
from dataclasses import dataclass
from google import genai
from google.genai import types

# Initialize Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_INSTRUCTION = """
You are an expert Commercial Real Estate Analyst. Your goal is to provide a comprehensive, professional, and data-driven analysis of a property based on its address.

You have access to Google Maps and Google Search to find real-time data.
Verify the location, tenant history, zoning, and nearby businesses.

Structure your response in two parts:
1. A detailed Markdown report. Use headers (##) for sections like "Property Overview", "Location Analysis", "Tenant Mix", "Market Trends", and "Investment Verdict".
2. A strictly formatted JSON block at the very end of the response containing numeric scores (0-100) and the estimated GPS coordinates for the property.

JSON Format:
```json
{
  "walkability": 85,
  "transit": 70,
  "marketStability": 90,
  "futureGrowth": 65,
  "amenityDensity": 80,
  "coordinates": {
    "lat": 40.7484,
    "lng": -73.9857
  }
}
```

IMPORTANT: You MUST provide the "coordinates" (lat/lng) in the JSON. Use the Google Maps tool to find the precise location.
"""


@dataclass
class Coordinates:
    lat: float
    lng: float


@dataclass
class PropertyScores:
    walkability: int
    transit: int
    market_stability: int
    future_growth: int
    amenity_density: int


@dataclass
class GroundingSource:
    uri: str
    title: str
    source_type: str  # "web" or "maps"


@dataclass
class AnalysisResult:
    markdown: str
    scores: Optional[PropertyScores]
    coordinates: Optional[Coordinates]
    grounding_sources: list[GroundingSource]


async def geocode_address(address: str) -> Optional[Coordinates]:
    """
    Geocode an address using Nominatim (OpenStreetMap).
    This is a fallback in case Gemini doesn't provide coordinates.
    """
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"format": "json", "q": address, "limit": 1},
                headers={
                    "User-Agent": "Worcester-CRE-Dashboard/1.0",
                    "Accept-Language": "en"
                }
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return Coordinates(
                        lat=float(data[0]["lat"]),
                        lng=float(data[0]["lon"])
                    )
    except Exception as e:
        print(f"Geocoding failed: {e}")

    return None


async def analyze_property(address: str, property_data: Optional[dict] = None) -> AnalysisResult:
    """
    Analyze a commercial property using Gemini 2.5 Flash with Google Search grounding.

    Args:
        address: The property address to analyze
        property_data: Optional additional property data from the database

    Returns:
        AnalysisResult with markdown analysis, scores, coordinates, and sources
    """

    # Build prompt with property context if available
    context_lines = []
    if property_data:
        if property_data.get("use_description"):
            context_lines.append(f"- Property Type: {property_data['use_description']}")
        if property_data.get("zoning"):
            context_lines.append(f"- Zoning: {property_data['zoning']}")
        if property_data.get("total_assessed_value"):
            context_lines.append(f"- Assessed Value: ${property_data['total_assessed_value']:,}")
        if property_data.get("lot_size_sqft"):
            context_lines.append(f"- Lot Size: {property_data['lot_size_sqft']:,} sqft")
        if property_data.get("year_built"):
            context_lines.append(f"- Year Built: {property_data['year_built']}")

    context = "\n".join(context_lines) if context_lines else "No additional property data available."

    prompt = f"""Analyze the commercial real estate property at: {address}

Known Property Information:
{context}

Focus on:
- Building details and history.
- Current commercial usage and key tenants.
- Neighborhood vibe and demographic suitability for business.
- Nearby competitors or complementary businesses.
- Pros and cons for a potential investor or commercial tenant.

Ensure you use Google Maps to find the exact location and surrounding context. Use Google Search to find recent news or listings."""

    # Configure Gemini with grounding tools
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[
            types.Tool(google_search=types.GoogleSearch())
        ],
        temperature=0.7,
    )

    # Run parallel: AI analysis + geocoding
    import asyncio

    # Start geocoding in background
    geo_task = asyncio.create_task(geocode_address(address))

    # Call Gemini
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config
    )

    # Wait for geocoding
    geo_coords = await geo_task

    full_text = response.text or "No analysis generated."

    # Extract JSON scores and AI-provided coordinates
    json_match = re.search(r'```json\n([\s\S]*?)\n```', full_text)
    scores: Optional[PropertyScores] = None
    markdown = full_text
    final_coordinates = geo_coords

    if json_match:
        try:
            parsed_data = json.loads(json_match.group(1))

            # Extract scores
            scores = PropertyScores(
                walkability=parsed_data.get("walkability", 50),
                transit=parsed_data.get("transit", 50),
                market_stability=parsed_data.get("marketStability", 50),
                future_growth=parsed_data.get("futureGrowth", 50),
                amenity_density=parsed_data.get("amenityDensity", 50)
            )

            # Fallback: If external geocoding failed, use AI's coordinates
            if not final_coordinates and parsed_data.get("coordinates"):
                coords = parsed_data["coordinates"]
                if coords.get("lat") and coords.get("lng"):
                    final_coordinates = Coordinates(
                        lat=coords["lat"],
                        lng=coords["lng"]
                    )

            # Remove JSON block from display text
            markdown = full_text.replace(json_match.group(0), "").strip()

        except json.JSONDecodeError as e:
            print(f"Failed to parse scores JSON: {e}")

    # Extract grounding sources from response metadata
    grounding_sources: list[GroundingSource] = []

    if hasattr(response, 'candidates') and response.candidates:
        candidate = response.candidates[0]
        if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
            metadata = candidate.grounding_metadata
            if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                for chunk in metadata.grounding_chunks:
                    if hasattr(chunk, 'web') and chunk.web:
                        grounding_sources.append(GroundingSource(
                            uri=chunk.web.uri,
                            title=chunk.web.title or "Web Source",
                            source_type="web"
                        ))

    return AnalysisResult(
        markdown=markdown,
        scores=scores,
        coordinates=final_coordinates,
        grounding_sources=grounding_sources
    )

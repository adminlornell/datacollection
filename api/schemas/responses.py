"""
Response schemas for the PropIntel AI API.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class ScoresResponse(BaseModel):
    """AI-generated property scores."""

    walkability: int = Field(..., ge=0, le=100, description="Walkability score")
    transit: int = Field(..., ge=0, le=100, description="Transit accessibility score")
    market_stability: int = Field(..., ge=0, le=100, description="Market stability score")
    future_growth: int = Field(..., ge=0, le=100, description="Future growth potential")
    amenity_density: int = Field(..., ge=0, le=100, description="Nearby amenity density")


class CoordinatesResponse(BaseModel):
    """Property coordinates."""

    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")


class SourceResponse(BaseModel):
    """Grounding source from AI analysis."""

    uri: str = Field(..., description="Source URL")
    title: str = Field(..., description="Source title")
    source_type: str = Field(..., description="Type: 'web' or 'maps'")


class AnalyzeResponse(BaseModel):
    """Full AI analysis response."""

    parcel_id: str = Field(..., description="Property parcel ID")
    scores: Optional[ScoresResponse] = Field(None, description="AI-generated scores")
    markdown: str = Field(..., description="Full analysis in Markdown format")
    coordinates: Optional[CoordinatesResponse] = Field(
        None, description="Property coordinates"
    )
    grounding_sources: List[SourceResponse] = Field(
        default_factory=list, description="Sources used in analysis"
    )
    cached: bool = Field(..., description="Whether result was from cache")
    analyzed_at: str = Field(..., description="ISO 8601 timestamp")


class CachedAnalysisResponse(BaseModel):
    """Response for cached analysis lookup."""

    exists: bool = Field(..., description="Whether cached analysis exists")
    data: Optional[AnalyzeResponse] = Field(None, description="Cached analysis data")

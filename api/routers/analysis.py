"""
Property analysis endpoints.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from supabase import Client

from api.schemas.requests import AnalyzeRequest
from api.schemas.responses import (
    AnalyzeResponse,
    CachedAnalysisResponse,
    ScoresResponse,
    CoordinatesResponse,
    SourceResponse,
)
from api.dependencies import get_supabase
from api.config import settings
from api.services.gemini import analyze_property

router = APIRouter(prefix="/api", tags=["Analysis"])


@router.get("/analysis/{parcel_id}", response_model=CachedAnalysisResponse)
async def get_cached_analysis(
    parcel_id: str,
    supabase: Optional[Client] = Depends(get_supabase)
):
    """
    Get cached AI analysis for a property if it exists.

    Returns exists=false if not yet analyzed or if database is unavailable.
    """
    if not supabase:
        return CachedAnalysisResponse(exists=False, data=None)

    try:
        result = supabase.table("worcester_data_collection").select(
            "parcel_id, ai_enriched, ai_enriched_at, "
            "ai_walkability_score, ai_transit_score, ai_market_stability_score, "
            "ai_future_growth_score, ai_amenity_density_score, "
            "ai_latitude, ai_longitude, ai_analysis_markdown, ai_grounding_sources"
        ).eq("parcel_id", parcel_id).single().execute()

        if result.data and result.data.get("ai_enriched"):
            data = result.data
            return CachedAnalysisResponse(
                exists=True,
                data=AnalyzeResponse(
                    parcel_id=parcel_id,
                    scores=ScoresResponse(
                        walkability=data.get("ai_walkability_score", 0),
                        transit=data.get("ai_transit_score", 0),
                        market_stability=data.get("ai_market_stability_score", 0),
                        future_growth=data.get("ai_future_growth_score", 0),
                        amenity_density=data.get("ai_amenity_density_score", 0)
                    ) if data.get("ai_walkability_score") else None,
                    markdown=data.get("ai_analysis_markdown", ""),
                    coordinates=CoordinatesResponse(
                        lat=data["ai_latitude"],
                        lng=data["ai_longitude"]
                    ) if data.get("ai_latitude") and data.get("ai_longitude") else None,
                    grounding_sources=[
                        SourceResponse(**s)
                        for s in (data.get("ai_grounding_sources") or [])
                    ],
                    cached=True,
                    analyzed_at=data.get("ai_enriched_at", "")
                )
            )

        return CachedAnalysisResponse(exists=False, data=None)

    except Exception as e:
        print(f"Error fetching cached analysis: {e}")
        return CachedAnalysisResponse(exists=False, data=None)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_property_endpoint(
    request: AnalyzeRequest,
    supabase: Optional[Client] = Depends(get_supabase)
):
    """
    Generate AI analysis for a property using Gemini 2.5 Flash.

    Results are cached in Supabase for future requests.
    """
    # Check for Gemini API key
    if not settings.validate_gemini():
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY not configured"
        )

    try:
        # Generate analysis
        result = await analyze_property(
            address=request.address,
            property_data=request.property_data
        )

        analyzed_at = datetime.utcnow().isoformat() + "Z"

        # Prepare response
        response = AnalyzeResponse(
            parcel_id=request.parcel_id,
            scores=ScoresResponse(
                walkability=result.scores.walkability,
                transit=result.scores.transit,
                market_stability=result.scores.market_stability,
                future_growth=result.scores.future_growth,
                amenity_density=result.scores.amenity_density
            ) if result.scores else None,
            markdown=result.markdown,
            coordinates=CoordinatesResponse(
                lat=result.coordinates.lat,
                lng=result.coordinates.lng
            ) if result.coordinates else None,
            grounding_sources=[
                SourceResponse(
                    uri=s.uri,
                    title=s.title,
                    source_type=s.source_type
                ) for s in result.grounding_sources
            ],
            cached=False,
            analyzed_at=analyzed_at
        )

        # Cache results in Supabase
        if supabase and result.scores:
            try:
                update_data = {
                    "ai_enriched": True,
                    "ai_enriched_at": analyzed_at,
                    "ai_walkability_score": result.scores.walkability,
                    "ai_transit_score": result.scores.transit,
                    "ai_market_stability_score": result.scores.market_stability,
                    "ai_future_growth_score": result.scores.future_growth,
                    "ai_amenity_density_score": result.scores.amenity_density,
                    "ai_analysis_markdown": result.markdown,
                    "ai_grounding_sources": [
                        {"uri": s.uri, "title": s.title, "source_type": s.source_type}
                        for s in result.grounding_sources
                    ]
                }

                if result.coordinates:
                    update_data["ai_latitude"] = result.coordinates.lat
                    update_data["ai_longitude"] = result.coordinates.lng

                supabase.table("worcester_data_collection").update(
                    update_data
                ).eq("parcel_id", request.parcel_id).execute()

            except Exception as e:
                print(f"Warning: Failed to cache analysis in Supabase: {e}")
                # Don't fail the request if caching fails

        return response

    except Exception as e:
        print(f"Analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )

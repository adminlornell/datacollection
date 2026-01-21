"""
PropIntel AI API - FastAPI Backend

Provides AI-powered property analysis using Gemini 2.5 Flash with Google Search grounding.
Caches results in Supabase for fast retrieval.
"""

import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

from gemini_service import analyze_property, PropertyScores, Coordinates, GroundingSource

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="PropIntel AI API",
    description="AI-powered commercial real estate analysis",
    version="1.0.0"
)

# Configure CORS for dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to dashboard domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("Warning: Supabase credentials not configured. Caching disabled.")
    supabase: Optional[Client] = None
else:
    supabase = create_client(supabase_url, supabase_key)


# Request/Response Models
class AnalyzeRequest(BaseModel):
    parcel_id: str
    address: str
    property_data: Optional[dict] = None


class ScoresResponse(BaseModel):
    walkability: int
    transit: int
    market_stability: int
    future_growth: int
    amenity_density: int


class CoordinatesResponse(BaseModel):
    lat: float
    lng: float


class SourceResponse(BaseModel):
    uri: str
    title: str
    source_type: str


class AnalyzeResponse(BaseModel):
    parcel_id: str
    scores: Optional[ScoresResponse]
    markdown: str
    coordinates: Optional[CoordinatesResponse]
    grounding_sources: list[SourceResponse]
    cached: bool
    analyzed_at: str


class CachedAnalysisResponse(BaseModel):
    exists: bool
    data: Optional[AnalyzeResponse]


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "PropIntel AI API"}


@app.get("/api/analysis/{parcel_id}", response_model=CachedAnalysisResponse)
async def get_cached_analysis(parcel_id: str):
    """
    Get cached AI analysis for a property if it exists.
    Returns exists=false if not yet analyzed.
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
                        SourceResponse(**s) for s in (data.get("ai_grounding_sources") or [])
                    ],
                    cached=True,
                    analyzed_at=data.get("ai_enriched_at", "")
                )
            )

        return CachedAnalysisResponse(exists=False, data=None)

    except Exception as e:
        print(f"Error fetching cached analysis: {e}")
        return CachedAnalysisResponse(exists=False, data=None)


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_property_endpoint(request: AnalyzeRequest):
    """
    Generate AI analysis for a property using Gemini 2.5 Flash.
    Results are cached in Supabase for future requests.
    """
    # Check for Gemini API key
    if not os.getenv("GEMINI_API_KEY"):
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

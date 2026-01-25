"""
Request schemas for the PropIntel AI API.
"""

from typing import Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request body for property analysis."""

    parcel_id: str = Field(..., description="Property parcel ID")
    address: str = Field(..., description="Property address")
    property_data: Optional[dict] = Field(
        None,
        description="Optional additional property context",
        json_schema_extra={
            "example": {
                "use_description": "Commercial",
                "zoning": "B1",
                "total_assessed_value": 500000,
                "lot_size_sqft": 25000,
                "year_built": 1995
            }
        }
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "parcel_id": "12345",
                "address": "360 Plantation St, Worcester, MA",
                "property_data": {
                    "use_description": "Commercial Office",
                    "total_assessed_value": 750000
                }
            }
        }
    }

"""
Pydantic models for owner enrichment data.
"""
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class OwnerType(str, Enum):
    """Type of property owner."""
    INDIVIDUAL = "individual"
    CORPORATION = "corporation"
    LLC = "llc"
    TRUST = "trust"
    PARTNERSHIP = "partnership"
    GOVERNMENT = "government"
    NONPROFIT = "nonprofit"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value):
        """Handle human-readable values from LLM."""
        if isinstance(value, str):
            value_lower = value.lower().strip()
            mappings = {
                "limited liability company": cls.LLC,
                "corporation": cls.CORPORATION,
                "corp": cls.CORPORATION,
                "individual": cls.INDIVIDUAL,
                "person": cls.INDIVIDUAL,
                "trust": cls.TRUST,
                "partnership": cls.PARTNERSHIP,
                "government": cls.GOVERNMENT,
                "nonprofit": cls.NONPROFIT,
                "non-profit": cls.NONPROFIT,
            }
            if value_lower in mappings:
                return mappings[value_lower]
        return cls.UNKNOWN


class DataSource(str, Enum):
    """Source of enrichment data."""
    MA_SOS = "ma_secretary_of_state"
    OPENCORPORATES = "opencorporates"
    SEC_EDGAR = "sec_edgar"
    WEB_SEARCH = "web_search"
    PROPERTY_RECORD = "property_record"

    @classmethod
    def _missing_(cls, value):
        """Handle human-readable values from LLM."""
        if isinstance(value, str):
            value_lower = value.lower().strip()
            mappings = {
                "ma secretary of state": cls.MA_SOS,
                "massachusetts secretary of state": cls.MA_SOS,
                "opencorporates": cls.OPENCORPORATES,
                "open corporates": cls.OPENCORPORATES,
                "sec edgar": cls.SEC_EDGAR,
                "sec": cls.SEC_EDGAR,
                "web search": cls.WEB_SEARCH,
                "duckduckgo": cls.WEB_SEARCH,
                "google": cls.WEB_SEARCH,
                "property record": cls.PROPERTY_RECORD,
            }
            if value_lower in mappings:
                return mappings[value_lower]
        return cls.WEB_SEARCH  # Default fallback


class SourceRecord(BaseModel):
    """Record of where data was found."""
    source: Union[DataSource, str]
    url: Optional[str] = None
    retrieved_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    raw_data: Optional[Dict[str, Any]] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator('retrieved_at', mode='before')
    @classmethod
    def normalize_retrieved_at(cls, v):
        if v is None:
            return datetime.utcnow()
        return v

    @field_validator('source', mode='before')
    @classmethod
    def normalize_source(cls, v):
        if isinstance(v, DataSource):
            return v
        if isinstance(v, str):
            v_lower = v.lower().strip()
            mappings = {
                "ma secretary of state": DataSource.MA_SOS,
                "massachusetts secretary of state": DataSource.MA_SOS,
                "ma_secretary_of_state": DataSource.MA_SOS,
                "opencorporates": DataSource.OPENCORPORATES,
                "open corporates": DataSource.OPENCORPORATES,
                "sec edgar": DataSource.SEC_EDGAR,
                "sec_edgar": DataSource.SEC_EDGAR,
                "web search": DataSource.WEB_SEARCH,
                "web_search": DataSource.WEB_SEARCH,
                "property record": DataSource.PROPERTY_RECORD,
                "property_record": DataSource.PROPERTY_RECORD,
            }
            return mappings.get(v_lower, DataSource.WEB_SEARCH)
        return DataSource.WEB_SEARCH


class Address(BaseModel):
    """Structured address."""
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: str = "USA"
    raw: Optional[str] = None  # Original unstructured address


class PersonInfo(BaseModel):
    """Information about an individual owner."""
    name: str
    role: Optional[str] = None  # e.g., "Owner", "Manager", "Registered Agent"
    address: Optional[Address] = None
    sources: List[SourceRecord] = Field(default_factory=list)


def normalize_owner_type(v):
    """Normalize owner type from various formats."""
    if isinstance(v, OwnerType):
        return v
    if isinstance(v, str):
        v_lower = v.lower().strip()
        mappings = {
            "individual": OwnerType.INDIVIDUAL,
            "person": OwnerType.INDIVIDUAL,
            "corporation": OwnerType.CORPORATION,
            "corp": OwnerType.CORPORATION,
            "llc": OwnerType.LLC,
            "limited liability company": OwnerType.LLC,
            "trust": OwnerType.TRUST,
            "partnership": OwnerType.PARTNERSHIP,
            "government": OwnerType.GOVERNMENT,
            "nonprofit": OwnerType.NONPROFIT,
            "non-profit": OwnerType.NONPROFIT,
            "unknown": OwnerType.UNKNOWN,
        }
        return mappings.get(v_lower, OwnerType.UNKNOWN)
    return OwnerType.UNKNOWN


class CompanyInfo(BaseModel):
    """Information about a company/entity owner."""
    name: str
    entity_type: Union[OwnerType, str] = OwnerType.UNKNOWN

    # Registration info
    state_of_formation: Optional[str] = None
    formation_date: Optional[str] = None
    status: Optional[str] = None  # Active, Dissolved, etc.
    entity_number: Optional[str] = None  # State filing number

    # Address
    registered_address: Optional[Address] = None
    principal_address: Optional[Address] = None

    # Key people
    registered_agent: Optional[PersonInfo] = None
    officers: Optional[List[PersonInfo]] = Field(default_factory=list)
    directors: Optional[List[PersonInfo]] = Field(default_factory=list)
    members: Optional[List[PersonInfo]] = Field(default_factory=list)  # For LLCs

    # Parent/subsidiary relationships
    parent_company: Optional[str] = None
    subsidiaries: Optional[List[str]] = Field(default_factory=list)

    # Sources
    sources: Optional[List[SourceRecord]] = Field(default_factory=list)

    @field_validator('entity_type', mode='before')
    @classmethod
    def validate_entity_type(cls, v):
        return normalize_owner_type(v)

    @model_validator(mode='before')
    @classmethod
    def handle_none_lists(cls, data):
        if isinstance(data, dict):
            for field in ['officers', 'directors', 'members', 'subsidiaries', 'sources']:
                if field in data and data[field] is None:
                    data[field] = []
        return data


class OwnershipLink(BaseModel):
    """A link in the ownership chain."""
    owner_name: str
    owner_type: Union[OwnerType, str] = OwnerType.UNKNOWN
    relationship: str = "owns"  # owns, manages, controls, etc.
    ownership_percentage: Optional[float] = None
    company_info: Optional[CompanyInfo] = None
    person_info: Optional[PersonInfo] = None
    sources: Optional[List[SourceRecord]] = Field(default_factory=list)

    @field_validator('owner_type', mode='before')
    @classmethod
    def validate_owner_type(cls, v):
        return normalize_owner_type(v)

    @model_validator(mode='before')
    @classmethod
    def handle_none_lists(cls, data):
        if isinstance(data, dict):
            if 'sources' in data and data['sources'] is None:
                data['sources'] = []
        return data


def normalize_data_source(v):
    """Normalize data source from various formats."""
    if isinstance(v, DataSource):
        return v
    if isinstance(v, str):
        v_lower = v.lower().strip()
        mappings = {
            "ma secretary of state": DataSource.MA_SOS,
            "massachusetts secretary of state": DataSource.MA_SOS,
            "ma_secretary_of_state": DataSource.MA_SOS,
            "opencorporates": DataSource.OPENCORPORATES,
            "open corporates": DataSource.OPENCORPORATES,
            "sec edgar": DataSource.SEC_EDGAR,
            "sec_edgar": DataSource.SEC_EDGAR,
            "web search": DataSource.WEB_SEARCH,
            "web_search": DataSource.WEB_SEARCH,
            "property record": DataSource.PROPERTY_RECORD,
            "property_record": DataSource.PROPERTY_RECORD,
        }
        return mappings.get(v_lower, DataSource.WEB_SEARCH)
    return DataSource.WEB_SEARCH


class OwnershipChain(BaseModel):
    """Complete ownership chain for a property."""
    property_parcel_id: str
    property_address: str
    original_owner_name: str
    original_owner_type: Union[OwnerType, str] = OwnerType.UNKNOWN

    # The ownership chain from property up to ultimate beneficial owners
    chain: Optional[List[OwnershipLink]] = Field(default_factory=list)

    # Ultimate beneficial owners (people at the top of the chain)
    ultimate_owners: Optional[List[PersonInfo]] = Field(default_factory=list)

    # Metadata
    research_completed: bool = False
    max_depth_reached: bool = False
    errors: Optional[List[str]] = Field(default_factory=list)
    researched_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    # All sources consulted
    sources_consulted: Optional[List[Union[DataSource, str]]] = Field(default_factory=list)

    @field_validator('researched_at', mode='before')
    @classmethod
    def normalize_researched_at(cls, v):
        if v is None:
            return datetime.utcnow()
        return v

    @field_validator('original_owner_type', mode='before')
    @classmethod
    def validate_owner_type(cls, v):
        return normalize_owner_type(v)

    @field_validator('sources_consulted', mode='before')
    @classmethod
    def validate_sources(cls, v):
        if v is None:
            return []
        return [normalize_data_source(s) for s in v]

    @model_validator(mode='before')
    @classmethod
    def handle_none_lists(cls, data):
        if isinstance(data, dict):
            for field in ['chain', 'ultimate_owners', 'errors', 'sources_consulted']:
                if field in data and data[field] is None:
                    data[field] = []
        return data


class ClassificationResult(BaseModel):
    """Result of classifying an owner name."""
    owner_name: str
    owner_type: OwnerType
    confidence: float = Field(ge=0.0, le=1.0)
    entity_indicators: List[str] = Field(default_factory=list)  # LLC, Inc, Trust, etc.
    reasoning: str = ""


class ResearchResult(BaseModel):
    """Result of researching a single entity."""
    entity_name: str
    entity_type: OwnerType
    found: bool = False
    company_info: Optional[CompanyInfo] = None
    person_info: Optional[PersonInfo] = None
    child_entities: List[str] = Field(default_factory=list)  # Entities to research next
    sources: List[SourceRecord] = Field(default_factory=list)
    error: Optional[str] = None

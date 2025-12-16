"""
Data models for Worcester MA property records.
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text,
    DateTime, ForeignKey, Boolean, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Street(Base):
    """Represents a street in Worcester MA."""
    __tablename__ = 'streets'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    url = Column(String(500))
    property_count = Column(Integer, default=0)
    scraped = Column(Boolean, default=False)
    scraped_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    properties = relationship("Property", back_populates="street")

    def __repr__(self):
        return f"<Street(name='{self.name}', properties={self.property_count})>"


class Property(Base):
    """Represents a property/parcel in Worcester MA."""
    __tablename__ = 'properties'

    id = Column(Integer, primary_key=True)

    # Location
    street_id = Column(Integer, ForeignKey('streets.id'))
    parcel_id = Column(String(100), unique=True)  # VGSI parcel identifier
    address = Column(String(500))
    location = Column(String(500))  # Full location string

    # Owner Information
    owner_name = Column(String(500))
    owner_address = Column(Text)

    # Property Details
    property_type = Column(String(100))  # Residential, Commercial, etc.
    land_use = Column(String(200))
    zoning = Column(String(100))
    neighborhood = Column(String(200))

    # Building Details
    year_built = Column(Integer)
    living_area = Column(Float)  # Square feet
    total_rooms = Column(Integer)
    bedrooms = Column(Integer)
    bathrooms = Column(Float)
    stories = Column(Float)
    building_style = Column(String(200))
    exterior_wall = Column(String(200))
    roof_type = Column(String(200))
    heating = Column(String(200))
    cooling = Column(String(200))

    # Land Details
    lot_size = Column(Float)  # Acres or sq ft
    frontage = Column(Float)
    depth = Column(Float)

    # Assessment Values
    land_value = Column(Float)
    building_value = Column(Float)
    total_value = Column(Float)

    # Additional Data (stored as JSON for flexibility)
    extra_features = Column(JSON)  # Garage, pool, fireplace, etc.
    building_details = Column(JSON)  # All building-specific details
    land_details = Column(JSON)  # All land-specific details
    sales_history = Column(JSON)  # List of past sales

    # URLs
    detail_url = Column(String(500))

    # Scraping metadata
    scraped = Column(Boolean, default=False)
    photos_downloaded = Column(Boolean, default=False)
    layout_downloaded = Column(Boolean, default=False)
    scraped_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    street = relationship("Street", back_populates="properties")
    photos = relationship("PropertyPhoto", back_populates="property")
    layouts = relationship("PropertyLayout", back_populates="property")

    def __repr__(self):
        return f"<Property(address='{self.address}', parcel_id='{self.parcel_id}')>"


class PropertyPhoto(Base):
    """Represents a photo of a property."""
    __tablename__ = 'property_photos'

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey('properties.id'))

    url = Column(String(500))  # Original URL
    local_path = Column(String(500))  # Local file path
    filename = Column(String(255))
    photo_type = Column(String(100))  # exterior, interior, aerial, etc.
    description = Column(Text)

    downloaded = Column(Boolean, default=False)
    download_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    property = relationship("Property", back_populates="photos")

    def __repr__(self):
        return f"<PropertyPhoto(property_id={self.property_id}, filename='{self.filename}')>"


class PropertyLayout(Base):
    """Represents a layout/sketch/floor plan of a property."""
    __tablename__ = 'property_layouts'

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey('properties.id'))

    url = Column(String(500))  # Original URL
    local_path = Column(String(500))  # Local file path
    filename = Column(String(255))
    layout_type = Column(String(100))  # sketch, floor_plan, site_plan, etc.

    downloaded = Column(Boolean, default=False)
    download_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    property = relationship("Property", back_populates="layouts")

    def __repr__(self):
        return f"<PropertyLayout(property_id={self.property_id}, type='{self.layout_type}')>"


class ScrapingProgress(Base):
    """Tracks overall scraping progress for resumability."""
    __tablename__ = 'scraping_progress'

    id = Column(Integer, primary_key=True)
    task_name = Column(String(100), unique=True)  # e.g., 'streets', 'properties'
    current_item = Column(String(500))  # Current street/property being processed
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    status = Column(String(50))  # pending, in_progress, completed, failed
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ScrapingProgress(task='{self.task_name}', status='{self.status}')>"


def init_database(db_path: str = "worcester_properties.db"):
    """Initialize the database and create all tables."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session

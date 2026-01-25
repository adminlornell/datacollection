-- Worcester Property Data - Database Setup
-- Run these queries in Supabase SQL Editor to set up the required tables

-- ============================================================================
-- Building Permits Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS building_permits (
    id SERIAL PRIMARY KEY,
    record_number TEXT UNIQUE,
    record_type TEXT,
    permit_for TEXT,
    date_submitted DATE,
    record_status TEXT,
    address TEXT,
    mbl TEXT,
    occupancy_type TEXT,
    permit_issued_date DATE,
    contractor_name TEXT,
    object_id INTEGER,
    linked_parcel_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for building_permits
CREATE INDEX IF NOT EXISTS idx_permits_mbl ON building_permits(mbl);
CREATE INDEX IF NOT EXISTS idx_permits_linked_parcel ON building_permits(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_permits_status ON building_permits(record_status);
CREATE INDEX IF NOT EXISTS idx_permits_type ON building_permits(permit_for);
CREATE INDEX IF NOT EXISTS idx_permits_address ON building_permits(address);
CREATE INDEX IF NOT EXISTS idx_permits_date ON building_permits(date_submitted);

-- ============================================================================
-- Business Certificates Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS business_certificates (
    id SERIAL PRIMARY KEY,
    certificate_number TEXT UNIQUE,
    business_name TEXT,
    address TEXT,
    file_date DATE,
    expiration_date DATE,
    object_id INTEGER,
    linked_parcel_id TEXT,
    is_expired BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for business_certificates
CREATE INDEX IF NOT EXISTS idx_certs_address ON business_certificates(address);
CREATE INDEX IF NOT EXISTS idx_certs_business ON business_certificates(business_name);
CREATE INDEX IF NOT EXISTS idx_certs_linked_parcel ON business_certificates(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_certs_expired ON business_certificates(is_expired);
CREATE INDEX IF NOT EXISTS idx_certs_expiration ON business_certificates(expiration_date);

-- ============================================================================
-- AI Enrichment Columns for worcester_data_collection
-- ============================================================================
-- Add AI enrichment columns if they don't exist
DO $$
BEGIN
    -- Enrichment tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_enriched') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_enriched BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_enriched_at') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_enriched_at TIMESTAMPTZ;
    END IF;

    -- AI Scores (0-100)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_walkability_score') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_walkability_score INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_transit_score') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_transit_score INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_market_stability_score') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_market_stability_score INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_future_growth_score') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_future_growth_score INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_amenity_density_score') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_amenity_density_score INTEGER;
    END IF;

    -- Coordinates
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_latitude') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_latitude DOUBLE PRECISION;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_longitude') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_longitude DOUBLE PRECISION;
    END IF;

    -- Analysis content
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_analysis_markdown') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_analysis_markdown TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'ai_grounding_sources') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN ai_grounding_sources JSONB;
    END IF;
END $$;

-- Index for AI enrichment
CREATE INDEX IF NOT EXISTS idx_worcester_ai_enriched
    ON worcester_data_collection(ai_enriched)
    WHERE ai_enriched = TRUE;

CREATE INDEX IF NOT EXISTS idx_worcester_coordinates
    ON worcester_data_collection(ai_latitude, ai_longitude)
    WHERE ai_latitude IS NOT NULL;

-- ============================================================================
-- Lead Management Columns
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_status') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_status TEXT DEFAULT 'new';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_priority') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_priority INTEGER DEFAULT 0;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_notes') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_notes TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_contact_name') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_contact_name TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_contact_email') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_contact_email TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_contact_phone') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_contact_phone TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'worcester_data_collection' AND column_name = 'lead_updated_at') THEN
        ALTER TABLE worcester_data_collection ADD COLUMN lead_updated_at TIMESTAMPTZ;
    END IF;
END $$;

-- Lead status index
CREATE INDEX IF NOT EXISTS idx_worcester_lead_status
    ON worcester_data_collection(lead_status);

CREATE INDEX IF NOT EXISTS idx_worcester_lead_priority
    ON worcester_data_collection(lead_priority)
    WHERE lead_priority > 0;

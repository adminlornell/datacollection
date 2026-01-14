-- Run this SQL in Supabase SQL Editor to create the required tables
-- Go to: Supabase Dashboard -> SQL Editor -> New Query

-- ============================================================
-- BUILDING PERMITS TABLE
-- ============================================================
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
CREATE INDEX IF NOT EXISTS idx_permits_address ON building_permits USING gin(address gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_permits_date ON building_permits(date_submitted);

-- ============================================================
-- BUSINESS CERTIFICATES TABLE
-- ============================================================
-- Drop and recreate if structure changed
DROP TABLE IF EXISTS business_certificates CASCADE;

CREATE TABLE business_certificates (
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
CREATE INDEX IF NOT EXISTS idx_certs_address ON business_certificates USING gin(address gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_certs_business ON business_certificates USING gin(business_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_certs_linked_parcel ON business_certificates(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_certs_expired ON business_certificates(is_expired);
CREATE INDEX IF NOT EXISTS idx_certs_exp_date ON business_certificates(expiration_date);

-- ============================================================
-- FUNCTION: Find Business Certificates by Property Location
-- ============================================================
CREATE OR REPLACE FUNCTION find_business_certificates(prop_location TEXT)
RETURNS TABLE (
    id INTEGER,
    certificate_number TEXT,
    business_name TEXT,
    address TEXT,
    file_date DATE,
    expiration_date DATE,
    is_expired BOOLEAN
) AS $$
DECLARE
    street_num TEXT;
    street_name TEXT;
BEGIN
    -- Extract street number and name from property location
    -- e.g., "123 MAIN ST" -> "123", "MAIN"
    street_num := (regexp_matches(prop_location, '^(\d+)'))[1];
    street_name := upper(regexp_replace(prop_location, '^\d+\s+', ''));
    street_name := split_part(street_name, ' ', 1);  -- First word of street name

    RETURN QUERY
    SELECT
        bc.id::INTEGER,
        bc.certificate_number,
        bc.business_name,
        bc.address,
        bc.file_date,
        bc.expiration_date,
        bc.is_expired
    FROM business_certificates bc
    WHERE
        -- Match street number and partial street name
        bc.address ILIKE street_num || ' ' || street_name || '%'
        OR bc.address ILIKE street_num || ' %' || street_name || '%'
    ORDER BY bc.is_expired ASC, bc.file_date DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: Get Permit Count by Parcel
-- ============================================================
CREATE OR REPLACE FUNCTION get_permit_counts()
RETURNS TABLE (
    parcel_id TEXT,
    permit_count BIGINT,
    latest_permit_date DATE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        bp.mbl as parcel_id,
        COUNT(*)::BIGINT as permit_count,
        MAX(bp.date_submitted) as latest_permit_date
    FROM building_permits bp
    WHERE bp.mbl IS NOT NULL
    GROUP BY bp.mbl;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- VIEW: Properties with Permit Summary
-- ============================================================
CREATE OR REPLACE VIEW property_permit_summary AS
SELECT
    wdc.parcel_id,
    wdc.location,
    wdc.owner_name,
    COUNT(bp.id) as permit_count,
    MAX(bp.date_submitted) as latest_permit,
    array_agg(DISTINCT bp.permit_for) FILTER (WHERE bp.permit_for IS NOT NULL) as permit_types
FROM worcester_data_collection wdc
LEFT JOIN building_permits bp ON wdc.parcel_id = bp.mbl
GROUP BY wdc.parcel_id, wdc.location, wdc.owner_name;

-- ============================================================
-- Update Dashboard Stats to include permits and certs
-- ============================================================
-- Refresh materialized view after import (if it exists)
-- REFRESH MATERIALIZED VIEW dashboard_stats;

-- ============================================================
-- VERIFY SETUP
-- ============================================================
SELECT 'Tables created successfully!' as status;
SELECT 'building_permits' as table_name, COUNT(*) as row_count FROM building_permits
UNION ALL
SELECT 'business_certificates', COUNT(*) FROM business_certificates;

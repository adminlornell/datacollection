-- ============================================================
-- RUN THIS SQL IN SUPABASE SQL EDITOR
-- Dashboard -> SQL Editor -> New Query -> Paste & Run
-- ============================================================

-- 1. DROP AND RECREATE BUSINESS CERTIFICATES TABLE
DROP TABLE IF EXISTS business_certificates CASCADE;

CREATE TABLE business_certificates (
    id SERIAL PRIMARY KEY,
    certificate_number TEXT,
    business_name TEXT,
    address TEXT,
    file_date DATE,
    expiration_date DATE,
    object_id INTEGER,
    linked_parcel_id TEXT,
    normalized_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_certs_cert_num ON business_certificates(certificate_number);
CREATE INDEX idx_certs_address ON business_certificates(address);
CREATE INDEX idx_certs_business ON business_certificates(business_name);
CREATE INDEX idx_certs_linked_parcel ON business_certificates(linked_parcel_id);
CREATE INDEX idx_certs_exp_date ON business_certificates(expiration_date);

-- 2. CREATE BUILDING PERMITS TABLE
DROP TABLE IF EXISTS building_permits CASCADE;

CREATE TABLE building_permits (
    id SERIAL PRIMARY KEY,
    record_number TEXT,
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

CREATE INDEX idx_permits_record ON building_permits(record_number);
CREATE INDEX idx_permits_mbl ON building_permits(mbl);
CREATE INDEX idx_permits_linked_parcel ON building_permits(linked_parcel_id);
CREATE INDEX idx_permits_status ON building_permits(record_status);
CREATE INDEX idx_permits_type ON building_permits(permit_for);
CREATE INDEX idx_permits_address ON building_permits(address);
CREATE INDEX idx_permits_date ON building_permits(date_submitted);

-- 3. VERIFY TABLES CREATED
SELECT 'Tables created successfully!' as status;
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('business_certificates', 'building_permits')
ORDER BY table_name, ordinal_position;

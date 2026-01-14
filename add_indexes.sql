-- Add indexes to speed up dashboard queries
-- Run this in Supabase SQL Editor

-- Building Permits indexes
CREATE INDEX IF NOT EXISTS idx_building_permits_record_status ON building_permits(record_status);
CREATE INDEX IF NOT EXISTS idx_building_permits_mbl ON building_permits(mbl);
CREATE INDEX IF NOT EXISTS idx_building_permits_date_submitted ON building_permits(date_submitted);
CREATE INDEX IF NOT EXISTS idx_building_permits_permit_for ON building_permits(permit_for);
CREATE INDEX IF NOT EXISTS idx_building_permits_address ON building_permits USING gin(address gin_trgm_ops);

-- Business Certificates indexes
CREATE INDEX IF NOT EXISTS idx_business_certificates_expiration_date ON business_certificates(expiration_date);
CREATE INDEX IF NOT EXISTS idx_business_certificates_linked_parcel_id ON business_certificates(linked_parcel_id);
CREATE INDEX IF NOT EXISTS idx_business_certificates_business_name ON business_certificates USING gin(business_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_business_certificates_address ON business_certificates USING gin(address gin_trgm_ops);

-- Properties indexes (worcester_data_collection)
CREATE INDEX IF NOT EXISTS idx_properties_parcel_id ON worcester_data_collection(parcel_id);
CREATE INDEX IF NOT EXISTS idx_properties_acct_number ON worcester_data_collection(acct_number);
CREATE INDEX IF NOT EXISTS idx_properties_location ON worcester_data_collection USING gin(location gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_properties_owner_name ON worcester_data_collection USING gin(owner_name gin_trgm_ops);

-- Increase statement timeout for this session (optional, run if needed)
-- SET statement_timeout = '60s';

-- Analyze tables to update statistics
ANALYZE building_permits;
ANALYZE business_certificates;
ANALYZE worcester_data_collection;

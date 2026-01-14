-- ============================================================
-- LINK BUSINESS CERTIFICATES TO PROPERTIES BY ADDRESS
-- Run this in Supabase SQL Editor after importing data
-- ============================================================

-- Step 1: Update linked_parcel_id by exact address match (case-insensitive)
UPDATE business_certificates bc
SET linked_parcel_id = wdc.parcel_id
FROM worcester_data_collection wdc
WHERE UPPER(TRIM(bc.address)) = UPPER(TRIM(wdc.location))
  AND bc.linked_parcel_id IS NULL;

-- Check how many were matched
SELECT 'Exact match count:' as step, COUNT(*) as matched
FROM business_certificates WHERE linked_parcel_id IS NOT NULL;

-- Step 2: Match by street number + first word of street name
-- For addresses like "123 MAIN ST" matching "123 MAIN STREET"
UPDATE business_certificates bc
SET linked_parcel_id = (
    SELECT wdc.parcel_id
    FROM worcester_data_collection wdc
    WHERE
        -- Extract and compare street number
        SUBSTRING(UPPER(TRIM(bc.address)) FROM '^([0-9]+)') = SUBSTRING(UPPER(TRIM(wdc.location)) FROM '^([0-9]+)')
        -- Extract and compare first word of street name
        AND SPLIT_PART(REGEXP_REPLACE(UPPER(TRIM(bc.address)), '^[0-9]+\s+', ''), ' ', 1) =
            SPLIT_PART(REGEXP_REPLACE(UPPER(TRIM(wdc.location)), '^[0-9]+\s+', ''), ' ', 1)
    LIMIT 1
)
WHERE bc.linked_parcel_id IS NULL
  AND bc.address IS NOT NULL;

-- Final count
SELECT 'Total linked certificates:' as step, COUNT(*) as linked
FROM business_certificates WHERE linked_parcel_id IS NOT NULL;

SELECT 'Unlinked certificates:' as step, COUNT(*) as unlinked
FROM business_certificates WHERE linked_parcel_id IS NULL;

-- Show sample of linked records
SELECT
    bc.certificate_number,
    bc.business_name,
    bc.address as cert_address,
    wdc.location as property_location,
    bc.linked_parcel_id
FROM business_certificates bc
JOIN worcester_data_collection wdc ON bc.linked_parcel_id = wdc.parcel_id
LIMIT 10;

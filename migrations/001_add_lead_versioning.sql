-- Migration: Add versioning to property_leads table for optimistic locking
-- Run this in your Supabase SQL Editor

-- Step 1: Add new columns
ALTER TABLE property_leads
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;

-- Step 2: Update existing rows to have version 1 and current timestamp
UPDATE property_leads
SET version = 1, updated_at = NOW()
WHERE version IS NULL;

-- Step 3: Make columns NOT NULL after populating
ALTER TABLE property_leads
ALTER COLUMN version SET NOT NULL,
ALTER COLUMN updated_at SET NOT NULL;

-- Step 4: Create function to auto-update timestamp and increment version
CREATE OR REPLACE FUNCTION update_lead_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Create trigger to call the function on updates
DROP TRIGGER IF EXISTS trigger_update_lead_version ON property_leads;

CREATE TRIGGER trigger_update_lead_version
    BEFORE UPDATE ON property_leads
    FOR EACH ROW
    EXECUTE FUNCTION update_lead_version();

-- Step 6: Create index on version for faster lookups
CREATE INDEX IF NOT EXISTS idx_property_leads_version ON property_leads(parcel_id, version);

-- Verify the changes
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'property_leads'
ORDER BY ordinal_position;

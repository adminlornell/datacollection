-- ============================================================
-- RUN THIS SQL IN SUPABASE SQL EDITOR
-- Dashboard -> SQL Editor -> New Query -> Paste & Run
-- ============================================================
-- This migration adds Row Level Security (RLS) to protect your tables
-- from unauthorized writes while allowing public read access.
-- ============================================================

-- ============================================================
-- STEP 1: ENABLE ROW LEVEL SECURITY ON ALL TABLES
-- ============================================================

ALTER TABLE worcester_data_collection ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE building_permits ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- STEP 2: PUBLIC READ-ONLY POLICIES
-- These allow anyone with the anon key to SELECT data
-- ============================================================

-- Worcester Data Collection (main property data)
CREATE POLICY "Allow public read access"
    ON worcester_data_collection
    FOR SELECT
    USING (true);

-- Business Certificates
CREATE POLICY "Allow public read access"
    ON business_certificates
    FOR SELECT
    USING (true);

-- Building Permits
CREATE POLICY "Allow public read access"
    ON building_permits
    FOR SELECT
    USING (true);

-- ============================================================
-- STEP 3: SERVICE ROLE FULL ACCESS POLICIES
-- These allow your Python scraper (using service_role key) to write data
-- ============================================================

-- Worcester Data Collection
CREATE POLICY "Service role full access"
    ON worcester_data_collection
    FOR ALL
    USING (auth.role() = 'service_role');

-- Business Certificates
CREATE POLICY "Service role full access"
    ON business_certificates
    FOR ALL
    USING (auth.role() = 'service_role');

-- Building Permits
CREATE POLICY "Service role full access"
    ON building_permits
    FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================
-- VERIFY RLS IS ENABLED
-- ============================================================
SELECT
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE tablename IN ('worcester_data_collection', 'business_certificates', 'building_permits');

-- ============================================================
-- VERIFY POLICIES WERE CREATED
-- ============================================================
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE tablename IN ('worcester_data_collection', 'business_certificates', 'building_permits')
ORDER BY tablename, policyname;

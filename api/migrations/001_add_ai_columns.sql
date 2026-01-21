-- Migration: Add AI Analysis columns to worcester_data_collection table
-- Run this in your Supabase SQL editor

-- AI Enrichment tracking
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_enriched BOOLEAN DEFAULT FALSE;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_enriched_at TIMESTAMPTZ;

-- AI Scores (0-100)
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_walkability_score INTEGER;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_transit_score INTEGER;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_market_stability_score INTEGER;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_future_growth_score INTEGER;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_amenity_density_score INTEGER;

-- AI-generated coordinates (from Gemini/geocoding)
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_latitude DOUBLE PRECISION;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_longitude DOUBLE PRECISION;

-- AI Analysis content
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_analysis_markdown TEXT;
ALTER TABLE worcester_data_collection ADD COLUMN IF NOT EXISTS ai_grounding_sources JSONB;

-- Index for faster lookups of enriched properties
CREATE INDEX IF NOT EXISTS idx_worcester_ai_enriched
ON worcester_data_collection (ai_enriched)
WHERE ai_enriched = TRUE;

-- Add comment for documentation
COMMENT ON COLUMN worcester_data_collection.ai_enriched IS 'Whether property has been analyzed by Gemini AI';
COMMENT ON COLUMN worcester_data_collection.ai_enriched_at IS 'Timestamp when AI analysis was performed';
COMMENT ON COLUMN worcester_data_collection.ai_walkability_score IS 'AI-generated walkability score (0-100)';
COMMENT ON COLUMN worcester_data_collection.ai_transit_score IS 'AI-generated transit accessibility score (0-100)';
COMMENT ON COLUMN worcester_data_collection.ai_market_stability_score IS 'AI-generated market stability score (0-100)';
COMMENT ON COLUMN worcester_data_collection.ai_future_growth_score IS 'AI-generated future growth potential score (0-100)';
COMMENT ON COLUMN worcester_data_collection.ai_amenity_density_score IS 'AI-generated amenity density score (0-100)';
COMMENT ON COLUMN worcester_data_collection.ai_latitude IS 'AI/geocoding determined latitude';
COMMENT ON COLUMN worcester_data_collection.ai_longitude IS 'AI/geocoding determined longitude';
COMMENT ON COLUMN worcester_data_collection.ai_analysis_markdown IS 'Full AI analysis in Markdown format';
COMMENT ON COLUMN worcester_data_collection.ai_grounding_sources IS 'JSON array of grounding sources used by Gemini';

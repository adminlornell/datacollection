/**
 * API Module
 *
 * Contains Supabase client initialization and all API/data fetching functions
 * for the Worcester Property Dashboard.
 *
 * Dependencies:
 * - Supabase JS library (loaded via CDN)
 * - config.js (for SUPABASE_URL, SUPABASE_KEY, AI_API_URL)
 */

// =============================================================================
// SUPABASE CLIENT INITIALIZATION
// =============================================================================

/**
 * Supabase client instance.
 * Initialized using createClient from the Supabase JS library.
 *
 * Usage:
 *   const { data, error } = await db.from('table_name').select('*');
 */
let db = null;

/**
 * Initialize the Supabase client.
 * Must be called after the Supabase library is loaded.
 *
 * @returns {Object} The Supabase client instance
 */
function initSupabaseClient() {
    if (typeof supabase === 'undefined') {
        console.error('Supabase library not loaded');
        return null;
    }

    const { createClient } = supabase;

    // Use config values if available, otherwise use defaults
    const url = typeof SUPABASE_URL !== 'undefined'
        ? SUPABASE_URL
        : 'https://cxcgeumhfjvnuibxnbob.supabase.co';

    const key = typeof SUPABASE_KEY !== 'undefined'
        ? SUPABASE_KEY
        : 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4Y2dldW1oZmp2bnVpYnhuYm9iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxOTc5MTYsImV4cCI6MjA3NDc3MzkxNn0.5p6YdLSEF54r-LVOPFhD4OpehMXx6K1q8RPWm3XKeS8';

    db = createClient(url, key);
    return db;
}

/**
 * Get the Supabase client instance, initializing if necessary.
 *
 * @returns {Object} The Supabase client instance
 */
function getSupabaseClient() {
    if (!db) {
        initSupabaseClient();
    }
    return db;
}

// =============================================================================
// DASHBOARD STATISTICS
// =============================================================================

/**
 * Fetches dashboard statistics from the materialized view.
 *
 * @returns {Promise<Object|null>} Dashboard stats object or null on error
 *
 * @example
 * const stats = await fetchDashboardStats();
 * // Returns: { total_properties, avg_assessed_value, avg_ownership_years, long_term_owners, last_updated }
 */
async function fetchDashboardStats() {
    try {
        const { data, error } = await getSupabaseClient()
            .from('dashboard_stats')
            .select('*')
            .single();

        if (error) throw error;
        return data;
    } catch (e) {
        console.error('Error fetching dashboard stats:', e);
        return null;
    }
}

// =============================================================================
// LEAD MANAGEMENT
// =============================================================================

/**
 * Fetches all property leads with full details.
 *
 * @returns {Promise<Array>} Array of lead objects
 *
 * @example
 * const leads = await fetchAllLeads();
 * // Returns: [{ id, parcel_id, status, follow_up_date, priority, notes, ... }]
 */
async function fetchAllLeads() {
    try {
        const { data, error } = await getSupabaseClient()
            .from('property_leads')
            .select('id, parcel_id, status, follow_up_date, priority, notes, contact_name, contact_phone, contact_email, version, updated_at');

        if (error) throw error;
        return data || [];
    } catch (e) {
        console.error('Error fetching leads:', e);
        return [];
    }
}

/**
 * Fetches a single lead by parcel ID.
 *
 * @param {string} parcelId - The parcel ID to look up
 * @returns {Promise<Object|null>} Lead object or null if not found
 */
async function fetchLeadByParcelId(parcelId) {
    try {
        const { data, error } = await getSupabaseClient()
            .from('property_leads')
            .select('*')
            .eq('parcel_id', parcelId)
            .single();

        if (error && error.code !== 'PGRST116') throw error; // PGRST116 = not found
        return data || null;
    } catch (e) {
        console.error('Error fetching lead:', e);
        return null;
    }
}

/**
 * Creates or updates a property lead.
 *
 * @param {Object} leadData - Lead data to save
 * @param {string} leadData.parcel_id - Required parcel ID
 * @param {string} [leadData.status] - Lead status
 * @param {number} [leadData.priority] - Priority (1-5)
 * @param {string} [leadData.notes] - Notes
 * @param {string} [leadData.follow_up_date] - Follow-up date (ISO format)
 * @param {string} [leadData.contact_name] - Contact name
 * @param {string} [leadData.contact_phone] - Contact phone
 * @param {string} [leadData.contact_email] - Contact email
 * @returns {Promise<{success: boolean, data: Object|null, error: string|null}>}
 */
async function saveLead(leadData) {
    try {
        const { data, error } = await getSupabaseClient()
            .from('property_leads')
            .upsert(leadData, { onConflict: 'parcel_id' })
            .select()
            .single();

        if (error) throw error;
        return { success: true, data, error: null };
    } catch (e) {
        console.error('Error saving lead:', e);
        return { success: false, data: null, error: e.message };
    }
}

/**
 * Deletes a property lead by parcel ID.
 *
 * @param {string} parcelId - The parcel ID to delete
 * @returns {Promise<{success: boolean, error: string|null}>}
 */
async function deleteLead(parcelId) {
    try {
        const { error } = await getSupabaseClient()
            .from('property_leads')
            .delete()
            .eq('parcel_id', parcelId);

        if (error) throw error;
        return { success: true, error: null };
    } catch (e) {
        console.error('Error deleting lead:', e);
        return { success: false, error: e.message };
    }
}

// =============================================================================
// BUSINESS CERTIFICATES
// =============================================================================

/**
 * Fetches parcel IDs that have linked business certificates.
 *
 * @returns {Promise<Array<string>>} Array of unique parcel IDs
 */
async function fetchBusinessCertParcelIds() {
    try {
        const { data, error } = await getSupabaseClient()
            .from('business_certificates')
            .select('linked_parcel_id')
            .not('linked_parcel_id', 'is', null);

        if (error) throw error;
        return [...new Set((data || []).map(d => d.linked_parcel_id))];
    } catch (e) {
        console.error('Error fetching business cert parcel IDs:', e);
        return [];
    }
}

/**
 * Fetches business certificates for a specific parcel.
 *
 * @param {string} parcelId - The parcel ID to look up
 * @returns {Promise<Array>} Array of certificate objects
 */
async function fetchBusinessCertsByParcel(parcelId) {
    try {
        const { data, error } = await getSupabaseClient()
            .from('business_certificates')
            .select('*')
            .eq('linked_parcel_id', parcelId)
            .order('expiration_date', { ascending: false });

        if (error) throw error;
        return data || [];
    } catch (e) {
        console.error('Error fetching business certificates:', e);
        return [];
    }
}

// =============================================================================
// PROPERTY DATA
// =============================================================================

/**
 * Fetches property details by parcel ID.
 *
 * @param {string} parcelId - The parcel ID to look up
 * @returns {Promise<Object|null>} Property object or null if not found
 */
async function fetchPropertyByParcelId(parcelId) {
    try {
        const { data, error } = await getSupabaseClient()
            .from('worcester_data_collection')
            .select('*')
            .eq('parcel_id', parcelId)
            .single();

        if (error) throw error;
        return data;
    } catch (e) {
        console.error('Error fetching property:', e);
        return null;
    }
}

/**
 * Fetches paginated property list with filters.
 *
 * @param {Object} options - Query options
 * @param {number} [options.page=1] - Page number (1-indexed)
 * @param {number} [options.pageSize=20] - Items per page
 * @param {string} [options.searchQuery] - Text search query
 * @param {string} [options.sortColumn='total_assessed_value'] - Column to sort by
 * @param {string} [options.sortDirection='desc'] - Sort direction ('asc' or 'desc')
 * @param {string} [options.propertyType] - Filter by property type
 * @param {Array<string>} [options.parcelIds] - Filter by specific parcel IDs
 * @param {Object} [options.advancedFilters] - Advanced filter options
 * @returns {Promise<{data: Array, error: string|null}>}
 */
async function fetchProperties(options = {}) {
    const {
        page = 1,
        pageSize = 20,
        searchQuery = '',
        sortColumn = 'total_assessed_value',
        sortDirection = 'desc',
        propertyType = 'all',
        parcelIds = null,
        advancedFilters = {}
    } = options;

    try {
        const from = (page - 1) * pageSize;
        const to = from + pageSize - 1;

        let query = getSupabaseClient()
            .from('worcester_data_collection')
            .select('parcel_id, location, owner_name, co_owner, total_assessed_value, year_built, living_area_sqft, bedrooms, bathrooms, building_style, use_description, use_code, neighborhood, ownership_years, last_sale_date, property_type');

        // Apply text search
        if (searchQuery && searchQuery.length >= 2) {
            query = query.or(`location.ilike.%${searchQuery}%,owner_name.ilike.%${searchQuery}%,parcel_id.ilike.%${searchQuery}%,neighborhood.ilike.%${searchQuery}%`);
        }

        // Apply parcel ID filter
        if (parcelIds && parcelIds.length > 0) {
            query = query.in('parcel_id', parcelIds);
        }

        // Apply property type filter
        if (propertyType !== 'all') {
            query = query.eq('property_type', propertyType);
        }

        // Apply advanced filters
        if (advancedFilters.address) {
            query = query.ilike('location', `%${advancedFilters.address}%`);
        }
        if (advancedFilters.owner) {
            query = query.or(`owner_name.ilike.%${advancedFilters.owner}%,co_owner.ilike.%${advancedFilters.owner}%`);
        }
        if (advancedFilters.minValue) {
            query = query.gte('total_assessed_value', advancedFilters.minValue);
        }
        if (advancedFilters.maxValue) {
            query = query.lte('total_assessed_value', advancedFilters.maxValue);
        }
        if (advancedFilters.minOwnership) {
            query = query.gte('ownership_years', advancedFilters.minOwnership);
        }
        if (advancedFilters.maxOwnership) {
            query = query.lte('ownership_years', advancedFilters.maxOwnership);
        }

        // Order and paginate
        const { data, error } = await query
            .order(sortColumn, { ascending: sortDirection === 'asc', nullsLast: true })
            .range(from, to);

        if (error) throw error;
        return { data: data || [], error: null };
    } catch (e) {
        console.error('Error fetching properties:', e);
        return { data: [], error: e.message };
    }
}

// =============================================================================
// AI ANALYSIS API
// =============================================================================

/**
 * Gets the AI API base URL from config or default.
 *
 * @returns {string} AI API URL
 */
function getAIApiUrl() {
    return typeof AI_API_URL !== 'undefined'
        ? AI_API_URL
        : 'https://propintel-api-560091322446.us-central1.run.app';
}

/**
 * Checks for cached AI analysis for a property.
 *
 * @param {string} parcelId - The parcel ID to check
 * @returns {Promise<{exists: boolean, data: Object|null}>}
 */
async function checkCachedAIAnalysis(parcelId) {
    try {
        const response = await fetch(`${getAIApiUrl()}/api/analysis/${parcelId}`);
        if (response.ok) {
            const result = await response.json();
            return result;
        }
    } catch (e) {
        console.warn('AI API not available:', e);
    }
    return { exists: false, data: null };
}

/**
 * Generates AI analysis for a property.
 *
 * @param {string} parcelId - The parcel ID
 * @param {Object} propertyData - Property data for analysis
 * @param {string} propertyData.location - Property address
 * @param {string} [propertyData.use_description] - Use description
 * @param {string} [propertyData.zoning] - Zoning code
 * @param {number} [propertyData.total_assessed_value] - Assessed value
 * @param {number} [propertyData.lot_size_sqft] - Lot size
 * @param {number} [propertyData.year_built] - Year built
 * @returns {Promise<{success: boolean, data: Object|null, error: string|null}>}
 */
async function generateAIAnalysis(parcelId, propertyData) {
    try {
        const response = await fetch(`${getAIApiUrl()}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                parcel_id: parcelId,
                address: propertyData.location + ', Worcester, MA',
                property_data: {
                    use_description: propertyData.use_description,
                    zoning: propertyData.zoning,
                    total_assessed_value: propertyData.total_assessed_value,
                    lot_size_sqft: propertyData.lot_size_sqft,
                    year_built: propertyData.year_built
                }
            })
        });

        if (!response.ok) {
            throw new Error('Analysis failed');
        }

        const result = await response.json();
        return { success: true, data: result, error: null };
    } catch (e) {
        console.error('AI Analysis error:', e);
        return { success: false, data: null, error: e.message };
    }
}

// =============================================================================
// EXPORTS (for module usage)
// =============================================================================

// Export API functions for use in other modules
// Note: When integrating with index.html, these will be global variables
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initSupabaseClient,
        getSupabaseClient,
        fetchDashboardStats,
        fetchAllLeads,
        fetchLeadByParcelId,
        saveLead,
        deleteLead,
        fetchBusinessCertParcelIds,
        fetchBusinessCertsByParcel,
        fetchPropertyByParcelId,
        fetchProperties,
        getAIApiUrl,
        checkCachedAIAnalysis,
        generateAIAnalysis
    };
}

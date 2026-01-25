/**
 * Global Configuration Module
 *
 * Contains all configuration constants, API URLs, and Supabase settings
 * for the Worcester Property Dashboard.
 */

// =============================================================================
// SUPABASE CONFIGURATION
// =============================================================================

/**
 * Supabase project URL
 * @type {string}
 */
const SUPABASE_URL = 'https://cxcgeumhfjvnuibxnbob.supabase.co';

/**
 * Supabase anonymous API key (public, safe to expose in client-side code)
 * @type {string}
 */
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4Y2dldW1oZmp2bnVpYnhuYm9iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxOTc5MTYsImV4cCI6MjA3NDc3MzkxNn0.5p6YdLSEF54r-LVOPFhD4OpehMXx6K1q8RPWm3XKeS8';

// =============================================================================
// AI API CONFIGURATION
// =============================================================================

/**
 * PropIntel AI API URL (Google Cloud Run deployment)
 * @type {string}
 */
const AI_API_URL = 'https://propintel-api-560091322446.us-central1.run.app';

// =============================================================================
// PAGINATION SETTINGS
// =============================================================================

/**
 * Default page size for property listings
 * @type {number}
 */
const DEFAULT_PAGE_SIZE = 20;

/**
 * Page size for certificate listings
 * @type {number}
 */
const CERT_PAGE_SIZE = 50;

/**
 * Page size for permit listings
 * @type {number}
 */
const PERMIT_PAGE_SIZE = 50;

// =============================================================================
// TOAST NOTIFICATION SETTINGS
// =============================================================================

/**
 * Duration in milliseconds for toast notifications
 * @type {number}
 */
const TOAST_DURATION = 3000;

// =============================================================================
// SEARCH SETTINGS
// =============================================================================

/**
 * Debounce delay in milliseconds for search input
 * @type {number}
 */
const SEARCH_DEBOUNCE_DELAY = 300;

/**
 * Minimum characters required to trigger search
 * @type {number}
 */
const MIN_SEARCH_LENGTH = 2;

// =============================================================================
// VALIDATION RULES
// =============================================================================

/**
 * Validation rules for lead form fields
 * @type {Object}
 */
const VALIDATION_RULES = {
    contact_email: {
        pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        message: 'Please enter a valid email address'
    },
    contact_phone: {
        pattern: /^[\d\s\-\(\)\+\.]{7,}$/,
        message: 'Please enter a valid phone number (min 7 digits)'
    }
};

// =============================================================================
// LEAD STATUS CONFIGURATION
// =============================================================================

/**
 * Human-readable labels for lead statuses
 * @type {Object}
 */
const LEAD_STATUS_LABELS = {
    'new': 'New',
    'contacted': 'Contacted',
    'interested': 'Interested',
    'hot': 'Hot',
    'follow_up': 'Follow-up',
    'not_interested': 'Not Interested',
    'closed': 'Closed'
};

// =============================================================================
// EXPORTS (for module usage)
// =============================================================================

// Export configuration for use in other modules
// Note: When integrating with index.html, these will be global variables
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        SUPABASE_URL,
        SUPABASE_KEY,
        AI_API_URL,
        DEFAULT_PAGE_SIZE,
        CERT_PAGE_SIZE,
        PERMIT_PAGE_SIZE,
        TOAST_DURATION,
        SEARCH_DEBOUNCE_DELAY,
        MIN_SEARCH_LENGTH,
        VALIDATION_RULES,
        LEAD_STATUS_LABELS
    };
}

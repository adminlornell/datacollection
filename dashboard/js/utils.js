/**
 * Utility Functions Module
 *
 * Contains general-purpose utility functions used throughout
 * the Worcester Property Dashboard.
 */

// =============================================================================
// NUMBER FORMATTING
// =============================================================================

/**
 * Formats a number with locale-specific thousand separators.
 *
 * @param {number|string|null} num - The number to format
 * @returns {string} Formatted number string (e.g., "1,234,567")
 *
 * @example
 * formatNumber(1234567) // Returns "1,234,567"
 * formatNumber(null)    // Returns "0"
 * formatNumber('')      // Returns "0"
 */
function formatNumber(num) {
    if (!num) return '0';
    return Number(num).toLocaleString();
}

/**
 * Formats a number as US currency.
 *
 * @param {number|string|null} amount - The amount to format
 * @returns {string} Formatted currency string (e.g., "$1,234,567")
 *
 * @example
 * formatCurrency(1234567)   // Returns "$1,234,567"
 * formatCurrency(null)      // Returns "$0"
 * formatCurrency(1234.56)   // Returns "$1,235" (rounded)
 */
function formatCurrency(amount) {
    if (!amount) return '$0';
    return '$' + formatNumber(Math.round(Number(amount)));
}

// =============================================================================
// STRING FORMATTING
// =============================================================================

/**
 * Converts a lead status key to a human-readable label.
 *
 * @param {string} status - The status key (e.g., 'not_interested')
 * @returns {string} Human-readable status label (e.g., 'Not Interested')
 *
 * @example
 * formatStatus('hot')            // Returns "Hot"
 * formatStatus('not_interested') // Returns "Not Interested"
 * formatStatus('unknown')        // Returns "unknown" (passthrough)
 */
function formatStatus(status) {
    const labels = {
        'new': 'New',
        'contacted': 'Contacted',
        'interested': 'Interested',
        'hot': 'Hot',
        'follow_up': 'Follow-up',
        'not_interested': 'Not Interested',
        'closed': 'Closed'
    };
    return labels[status] || status;
}

/**
 * Escapes HTML special characters to prevent XSS attacks.
 * Uses string replacement method for predictable output.
 *
 * @param {string|null} text - The text to escape
 * @returns {string} HTML-escaped text safe for DOM insertion
 *
 * @example
 * escapeHtml('<script>alert("xss")</script>')
 * // Returns "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"
 *
 * escapeHtml(null) // Returns ""
 */
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * Alternative escapeHtml implementation using DOM.
 * Creates a text node and extracts its escaped HTML representation.
 *
 * @param {string|null} text - The text to escape
 * @returns {string} HTML-escaped text
 *
 * @example
 * escapeHtmlDOM('<div>test</div>') // Returns "&lt;div&gt;test&lt;/div&gt;"
 */
function escapeHtmlDOM(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// TOAST NOTIFICATIONS
// =============================================================================

/**
 * Displays a toast notification message.
 * Note: This function accepts HTML content for formatting purposes.
 * Always use escapeHtml() on user-provided content before passing to this function.
 *
 * @param {string} message - The message to display (trusted HTML content only)
 * @param {string} [type='info'] - The toast type: 'info', 'success', 'warning', or 'error'
 * @returns {void}
 *
 * @example
 * showToast('Changes saved successfully', 'success')
 * showToast('Error occurred', 'error')
 * showToast('Please wait...', 'info')
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        console.warn('Toast container not found');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    // Note: message should be trusted content or pre-escaped with escapeHtml()
    // This preserves the original behavior from index.html
    toast.textContent = message;
    container.appendChild(toast);

    // Auto-remove after duration (default 3 seconds)
    const duration = typeof TOAST_DURATION !== 'undefined' ? TOAST_DURATION : 3000;
    setTimeout(() => toast.remove(), duration);
}

// =============================================================================
// DEBOUNCING
// =============================================================================

/**
 * Creates a debounced version of a function that delays execution
 * until after the specified wait time has elapsed since the last call.
 *
 * @param {Function} func - The function to debounce
 * @param {number} wait - The delay in milliseconds
 * @returns {Function} Debounced function
 *
 * @example
 * const debouncedSearch = debounce((query) => {
 *     console.log('Searching for:', query);
 * }, 300);
 *
 * // Called multiple times rapidly, but only executes once after 300ms
 * debouncedSearch('test');
 * debouncedSearch('testing');
 * debouncedSearch('testing123'); // Only this one executes
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Creates a throttled version of a function that only allows execution
 * once per specified time period.
 *
 * @param {Function} func - The function to throttle
 * @param {number} limit - The minimum time between executions in milliseconds
 * @returns {Function} Throttled function
 *
 * @example
 * const throttledScroll = throttle(() => {
 *     console.log('Scroll event');
 * }, 100);
 *
 * window.addEventListener('scroll', throttledScroll);
 */
function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// =============================================================================
// VALIDATION
// =============================================================================

/**
 * Validates a field value against predefined validation rules.
 *
 * @param {string} field - The field name to validate (e.g., 'contact_email')
 * @param {string} value - The value to validate
 * @returns {{valid: boolean, message: string|null}} Validation result
 *
 * @example
 * validateField('contact_email', 'test@example.com')
 * // Returns { valid: true, message: null }
 *
 * validateField('contact_email', 'invalid')
 * // Returns { valid: false, message: 'Please enter a valid email address' }
 */
function validateField(field, value) {
    // Use global VALIDATION_RULES if available, otherwise use local definition
    const rules = typeof VALIDATION_RULES !== 'undefined' ? VALIDATION_RULES : {
        contact_email: {
            pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
            message: 'Please enter a valid email address'
        },
        contact_phone: {
            pattern: /^[\d\s\-\(\)\+\.]{7,}$/,
            message: 'Please enter a valid phone number (min 7 digits)'
        }
    };

    const rule = rules[field];
    if (!rule) {
        return { valid: true, message: null };
    }

    // Empty values are considered valid (not required)
    if (!value || value.trim() === '') {
        return { valid: true, message: null };
    }

    const isValid = rule.pattern.test(value);
    return {
        valid: isValid,
        message: isValid ? null : rule.message
    };
}

// =============================================================================
// LOCAL STORAGE HELPERS
// =============================================================================

/**
 * Safely retrieves and parses JSON from localStorage.
 *
 * @param {string} key - The localStorage key
 * @param {*} defaultValue - Default value if key doesn't exist or parse fails
 * @returns {*} Parsed value or default value
 *
 * @example
 * getLocalStorage('recentSearches', [])
 * // Returns stored array or empty array if not found
 */
function getLocalStorage(key, defaultValue = null) {
    try {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : defaultValue;
    } catch (e) {
        console.warn(`Error reading localStorage key "${key}":`, e);
        return defaultValue;
    }
}

/**
 * Safely stores a value as JSON in localStorage.
 *
 * @param {string} key - The localStorage key
 * @param {*} value - The value to store (will be JSON stringified)
 * @returns {boolean} True if successful, false otherwise
 *
 * @example
 * setLocalStorage('recentSearches', ['term1', 'term2'])
 */
function setLocalStorage(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch (e) {
        console.warn(`Error writing localStorage key "${key}":`, e);
        return false;
    }
}

// =============================================================================
// DATE HELPERS
// =============================================================================

/**
 * Formats a date string to a localized date format.
 *
 * @param {string|Date} date - The date to format
 * @returns {string} Formatted date string
 *
 * @example
 * formatDate('2024-01-15') // Returns "1/15/2024" (in US locale)
 */
function formatDate(date) {
    if (!date) return '';
    return new Date(date).toLocaleDateString();
}

/**
 * Gets today's date in ISO format (YYYY-MM-DD).
 *
 * @returns {string} Today's date in ISO format
 *
 * @example
 * getTodayISO() // Returns "2024-01-15"
 */
function getTodayISO() {
    return new Date().toISOString().split('T')[0];
}

// =============================================================================
// EXPORTS (for module usage)
// =============================================================================

// Export utilities for use in other modules
// Note: When integrating with index.html, these will be global variables
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        formatNumber,
        formatCurrency,
        formatStatus,
        escapeHtml,
        escapeHtmlDOM,
        showToast,
        debounce,
        throttle,
        validateField,
        getLocalStorage,
        setLocalStorage,
        formatDate,
        getTodayISO
    };
}

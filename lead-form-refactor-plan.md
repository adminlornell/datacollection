# Lead Management Form Refactor Plan

## Status: COMPLETED

All four phases have been successfully implemented.

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Core Save Control |
| Phase 2 | ✅ Complete | Validation |
| Phase 3 | ✅ Complete | Better Feedback |
| Phase 4 | ✅ Complete | Data Integrity |

---

## Overview

The lead management form in `cre_dashboard.html` has been refactored from auto-save to manual save with full CRUD control.

**Before**: Data saved automatically on every keystroke (500ms debounce)
**After**: Explicit save control with validation, dirty tracking, and conflict resolution

---

## Implementation Summary

### Phase 1: Core Save Control ✅

**New State Variables** (Line 2321-2324):
- `pendingLeadChanges = {}` - Stores unsaved field values
- `isLeadFormDirty = false` - Tracks dirty state
- `lastSavedTimestamp = {}` - Tracks save times per parcel

**New Functions** (Lines 3062-3160):
- `setLeadField(field, value)` - Track changes without saving
- `hasUnsavedChanges()` - Check for pending changes
- `clearPendingChanges()` - Reset pending state
- `updateDirtyIndicator()` - Update UI indicator
- `saveLeadForm()` - Commit all changes with validation
- `cancelLeadChanges()` - Discard changes
- `selectStatus(btn, status)` - UI-only status selection
- `selectPriority(priority)` - UI-only priority selection

**Form HTML Changes** (Lines 2839-2932):
- Removed all `oninput`/`onchange` auto-save handlers
- Added dirty indicator element
- Replaced buttons with Save Lead, Cancel, Delete

**Navigate-Away Warning** (Lines 2352-2358):
- `beforeunload` event listener warns on page close
- `selectProperty()` warns when switching with unsaved changes

**CSS** (Lines 1054-1064):
- `.dirty-indicator` - Orange warning box

---

### Phase 2: Validation ✅

**Validation Rules** (Lines 3196-3205):
- `contact_email`: `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`
- `contact_phone`: `/^[\d\s\-\(\)\+\.]{7,}$/`

**New Functions** (Lines 3207-3270):
- `validateField(field, value)` - Validate single field
- `showFieldError(fieldId, message)` - Show/clear inline errors
- `validateLeadForm()` - Validate all pending changes

**Real-time Validation** (Lines 3072-3080):
- Errors shown immediately as user types
- Errors clear when input becomes valid

**Form HTML Changes** (Lines 2875, 2881):
- Added error message elements for phone and email

**CSS** (Lines 1066-1090):
- `.lead-input.input-error` - Red border and background
- `.field-error` - Red error text with warning icon

---

### Phase 3: Better Feedback ✅

**New Functions** (Lines 3277-3326):
- `formatLastSaved(parcelId)` - Format timestamp as relative time
- `updateLastSavedDisplay()` - Update UI element
- `saveLeadWithRetry(updates, maxRetries)` - Retry with exponential backoff

**Save Function Updates** (Lines 3119-3148):
- Uses retry logic (3 attempts with 1s, 2s, 4s delays)
- Updates timestamp on success
- Shows loading spinner during save

**Form HTML Changes** (Lines 2930-2932):
- Added last saved display element

**CSS** (Lines 1092-1128):
- `.btn-loading` - Spinning loader animation
- `.last-saved-display` - Green success box

---

### Phase 4: Data Integrity ✅

**SQL Migration** (`migrations/001_add_lead_versioning.sql`):
- Adds `updated_at` TIMESTAMP column
- Adds `version` INTEGER column
- Creates trigger to auto-increment version
- Creates index for performance

**Updated Functions** (Lines 3375-3471):
- `saveLead(updates)` - Now uses optimistic locking with version check
- `refreshLeadData(parcelId)` - Fetch latest data on conflict

**Query Updates** (Line 2500-2501):
- `loadLeadsCounts()` now includes `id`, `version`, `updated_at`

**Conflict Resolution**:
- Detects when another user/tab modified the lead
- Shows dialog with options: Refresh or Keep Changes

---

## File Changes Summary

### cre_dashboard.html

| Section | Lines | Changes |
|---------|-------|---------|
| CSS | 1054-1128 | Dirty indicator, validation errors, loading spinner, last saved |
| State Variables | 2321-2324 | pendingLeadChanges, isLeadFormDirty, lastSavedTimestamp |
| Init | 2352-2358 | beforeunload warning |
| loadLeadsCounts | 2500-2501 | Added id, version, updated_at to query |
| selectProperty | 2810-2816 | Unsaved changes warning |
| Form HTML | 2839-2932 | New handlers, dirty indicator, buttons, error elements |
| Phase 1 Functions | 3062-3160 | State management, save, cancel |
| Phase 2 Functions | 3196-3270 | Validation rules and functions |
| Phase 3 Functions | 3277-3326 | Timestamp formatting, retry logic |
| saveLead | 3375-3471 | Optimistic locking, conflict resolution |

### New Files

| File | Purpose |
|------|---------|
| `migrations/001_add_lead_versioning.sql` | Database schema update for Phase 4 |

---

## Deployment Checklist

### Phase 1-3 (No database changes required)
- [x] Deploy updated `cre_dashboard.html`
- [x] Test form saves correctly
- [x] Test dirty indicator appears
- [x] Test cancel discards changes
- [x] Test validation blocks invalid saves
- [x] Test loading spinner shows
- [x] Test retry logic on network failure

### Phase 4 (Database migration required)
- [ ] Run `migrations/001_add_lead_versioning.sql` in Supabase SQL Editor
- [ ] Verify columns added: `updated_at`, `version`
- [ ] Verify trigger created: `trigger_update_lead_version`
- [ ] Test conflict detection with two browser tabs

---

## Testing Checklist

### Phase 1 Tests
- [x] Form fields no longer auto-save on input
- [x] Dirty indicator appears when fields are modified
- [x] Save button commits all pending changes
- [x] Cancel button discards changes and resets form
- [x] Navigate-away warning appears with unsaved changes
- [x] Switching properties warns about unsaved changes

### Phase 2 Tests
- [x] Invalid email shows error message in real-time
- [x] Invalid phone shows error message in real-time
- [x] Save is blocked when validation fails
- [x] Errors clear when valid input is entered

### Phase 3 Tests
- [x] Loading spinner shows during save
- [x] Last saved timestamp displays correctly
- [x] Retry logic works on network failure
- [x] Success/error toasts are clear

### Phase 4 Tests
- [ ] Version increments on each save
- [ ] Conflict detected when saving stale data
- [ ] Refresh option loads latest data
- [ ] Keep Changes option preserves local edits

---

## Architecture After Refactor

### New Data Flow
```
User modifies field
    ↓
setLeadField() stores in pendingLeadChanges
    ↓
updateDirtyIndicator() shows "Unsaved changes"
    ↓
[Real-time validation runs]
    ↓
User clicks "Save Lead"
    ↓
validateLeadForm() checks all fields
    ↓ (if valid)
saveLeadWithRetry() attempts save (up to 3 times)
    ↓
saveLead() with optimistic locking
    ↓ (if version matches)
Database updated, version incremented
    ↓
clearPendingChanges(), updateLastSavedDisplay()
    ↓
"Lead saved successfully" toast
```

### Conflict Resolution Flow
```
saveLead() detects version mismatch
    ↓
User sees: "This lead was modified by another user"
    ↓
[OK] → refreshLeadData() loads latest, clears pending
[Cancel] → User keeps changes, can retry save
```

---

## Security Notes

- All user input escaped with `escapeHtml()` before rendering
- `textContent` used instead of `innerHTML` for dynamic content
- Client-side validation is for UX only; server-side validation via Supabase RLS recommended
- Version field prevents lost updates from concurrent edits

---

## Rollback Instructions

If issues arise, revert to auto-save behavior:

1. Restore original `cre_dashboard.html` from git
2. Phase 4 database columns can remain (backwards compatible)
3. No data migration needed for rollback

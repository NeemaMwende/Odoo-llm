# Vector Search Implementation Status

**Date**: 2025-10-18
**Status**: ⚠️ NON-FUNCTIONAL - Reverted recent changes
**Branch**: 18.0-migrate-knowledge-modules

## What Was Completed

### Successfully Migrated Modules

1. **llm_pgvector** ✅
   - Fixed Odoo 18 compatibility issues:
     - Changed `fields.Default` → `SENTINEL` pattern for optional parameters
     - Fixed `pre_init_hook(cr)` → `pre_init_hook(env)` signature
     - Fixed deprecated `attrs` attribute in views
   - PostgreSQL pgvector extension working correctly
   - No separate connection URI needed (uses Odoo database)

2. **llm_knowledge** ✅ (partially)
   - Fixed view modes: `tree` → `list` in actions
   - Fixed deprecated `states` and `attrs` attributes in wizards
   - Fixed `search(count=True)` → `search_count()` migration
   - Core resource and chunk models working

## Current Blocker: Vector Search Not Functional

### The Problem

Vector similarity search from the UI searchbar is **not working correctly**. The issue involves:

1. **Search method complexity**: The `search()` method override in `llm.knowledge.chunk` is handling vector search
2. **Order preservation**: Results are sorted by `sequence, id` instead of similarity score
3. **`_search_embedding()` method**: Custom search method for the virtual `embedding` field

### What Was Tried (and Reverted)

#### Attempt 1: `_search_embedding()` Method
- Added custom `search='_search_embedding'` to the `embedding` field
- This method is called by Odoo when searching with `[('embedding', '=', 'search term')]`
- **Problem**: Led to complex flow with context passing and multiple search() calls

#### Attempt 2: Context-based Order Preservation
- Tried passing `vector_search_ordered_ids` in context from `_vector_search_aggregate()`
- Tried detecting this in `search()` to re-order results
- **Problem**: Context doesn't persist when `_search_embedding()` returns a domain and Odoo calls `search()` again

### Architecture Issues Identified

The current flow is convoluted:

1. UI calls `search([('embedding', '=', 'rabbit habitat')], order='sequence,id')`
2. Odoo calls `_search_embedding('=', 'rabbit habitat')`
3. `_search_embedding()` calls `search([], vector_search_term='...')` internally
4. Vector search happens, returns recordset with similarity scores in context
5. `_search_embedding()` extracts IDs and returns domain `[('id', 'in', [...])]`
6. **Odoo calls `search()` AGAIN** with that domain + original `order` parameter
7. Results get re-sorted by sequence, losing similarity order

**Root cause**: `_search_embedding()` must return a domain (not a recordset), so Odoo re-applies the domain with the original order parameter, destroying our custom ordering.

## What Needs Investigation

### Option 1: Remove `_search_embedding()` Entirely
- Keep the `search()` override to handle embedding domains directly
- Parse the domain in `search()` and do vector search there
- Don't use the `search` parameter on the field at all
- **Question**: Will Odoo still allow searching on a non-stored field without a search method?

### Option 2: Override `_order` Dynamically
- Detect vector search and temporarily change model's `_order` attribute
- Reset it after search completes
- **Risk**: Thread safety issues, side effects

### Option 3: Post-process Results in RPC Layer
- Let search return results in default order
- Have the controller/RPC endpoint re-order by similarity from context
- **Downside**: Breaks Odoo's standard search API contract

### Option 4: Check Odoo Source Code Examples
- Look for other Odoo modules that do custom similarity/scoring searches
- See how they handle order preservation
- Example: product search with relevance scores, full-text search modules

## Code State After Revert

The `llm.knowledge.chunk` model currently has:
- `embedding` field defined as virtual field (no `search` parameter)
- `search()` method that handles vector search when it finds embedding domain
- `_vector_search_aggregate()` helper method
- Results returned with `similarity_scores` in context

**Missing**:
- No mechanism to preserve similarity-based order when called from UI
- No `_search_embedding()` method (reverted)
- No context-based order preservation logic (reverted)

## Next Steps (When Resuming)

1. **Research Odoo patterns** for custom-ordered searches
   - Check mail module for message relevance ordering
   - Check product/website modules for search ranking
   - Look for similar vector search implementations

2. **Test basic vector search functionality**
   - Verify vector search works programmatically: `chunk_obj.search([], query_vector=..., collection_id=...)`
   - Verify it works with embedding term: `chunk_obj.search([('embedding', '=', 'test')])`
   - Check if results contain similarity scores in context

3. **Solve the ordering issue**
   - Based on research, implement proper solution
   - Test from UI searchbar
   - Verify results are ordered by similarity

4. **Clean up and document**
   - Remove debug logging
   - Add clear docstrings
   - Document the final pattern for future reference

## Questions to Answer

1. How do other Odoo modules handle custom result ordering (not based on DB columns)?
2. Is there a way to make `_search_embedding()` return an ordered domain?
3. Should we use a stored `similarity` field that gets updated during search?
4. Can we override `_search()` (with underscore) instead of `search()` to intercept earlier?

## Files Involved

- `llm_knowledge/models/llm_knowledge_chunk.py` - Main search logic
- `llm_knowledge/models/llm_knowledge_collection.py` - `search_vectors()` method
- `llm_pgvector/models/llm_store.py` - Vector store implementation
- `llm_pgvector/fields.py` - PgVector field type

## Testing Checklist (For When Fixed)

- [ ] Basic search works: `search([('embedding', '=', 'test')])`
- [ ] Results are ordered by similarity (highest first)
- [ ] Similarity scores available in context
- [ ] Works from UI searchbar
- [ ] Works with additional domain filters
- [ ] Works with limit and offset
- [ ] Works with multiple collections
- [ ] Works with specific collection_id parameter

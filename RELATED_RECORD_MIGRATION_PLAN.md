# Related Record Component - Migration Plan (16.0 → 18.0)

## Executive Summary

The **Related Record** component allows users to link LLM chat threads to any Odoo record (customers, orders, projects, etc.). This component existed in Odoo 16.0 but was **completely missing** from the 18.0 migration. This document provides a comprehensive plan to re-implement it using Odoo 18.0 architecture patterns.

---

## Current Status

### Backend Status: ✅ Complete
The backend fields and logic are **already implemented** and functional:

| Field | Type | Purpose | Status |
|-------|------|---------|--------|
| `llm_thread.model` | Char | Technical name of linked model | ✅ Present |
| `llm_thread.res_id` | Many2oneReference | ID of linked record | ✅ Present |
| `RelatedRecordProxy` | Python Class | Template helper for accessing record fields | ✅ Present |

**Source Files:**
- `llm_thread/models/llm_thread.py:127-134` - Field definitions
- `llm_thread/models/llm_thread.py:15-92` - RelatedRecordProxy class

### Frontend Status: ❌ Missing
The frontend UI component is **completely missing**:

| Component File | 16.0 Location | 18.0 Status |
|---------------|---------------|-------------|
| llm_chat_thread_related_record.js | `llm_thread/static/src/components/` | ❌ Missing |
| llm_chat_thread_related_record.xml | `llm_thread/static/src/components/` | ❌ Missing |
| llm_chat_thread_related_record.scss | `llm_thread/static/src/components/` | ❌ Missing |

---

## Feature Inventory - 16.0 Baseline

### 1. Display Linked Record ✅
**16.0 Implementation:**
- Shows record display name with model-specific icon
- Loading spinner while fetching display name
- Uses `name_get()` RPC call to fetch display name
- Icon mapping for 15+ common models (partner, sale, project, etc.)

**Code Reference:**
```javascript
// llm_thread/static/src/components/llm_chat_thread_related_record/llm_chat_thread_related_record.js:81-97
async _loadRelatedRecordDisplayName() {
    const result = await this.messaging.rpc({
        model: this.thread.relatedThreadModel,
        method: "name_get",
        args: [[this.thread.relatedThreadId]],
    });
    this.state.relatedRecordDisplayName = result[0][1];
}
```

**Model Icon Mapping (16.0):**
```javascript
// Lines 101-127
const iconMap = {
    "res.partner": "fa-user",
    "sale.order": "fa-shopping-cart",
    "purchase.order": "fa-shopping-bag",
    "account.move": "fa-file-text-o",
    "project.project": "fa-folder-open",
    "project.task": "fa-check-square-o",
    "helpdesk.ticket": "fa-ticket",
    "crm.lead": "fa-bullseye",
    // ... 15 models total
};
```

### 2. Open Linked Record ✅
**16.0 Implementation:**
- Click on record name → opens form view
- Uses `env.services.action.doAction()` with `target: "current"`
- Shows error notification if open fails

**Code Reference:**
```javascript
// Lines 135-154
async onClickRelatedRecord() {
    await this.env.services.action.doAction({
        type: "ir.actions.act_window",
        res_model: this.thread.relatedThreadModel,
        res_id: this.thread.relatedThreadId,
        views: [[false, "form"]],
        target: "current",
    });
}
```

### 3. Link New Record (Record Picker) ✅
**16.0 Implementation:**

#### Step 1: Model Selection
- Dropdown with all available models
- Fetches models via `ir.model.search_read()`
- Filters: `transient=false`, excludes mail models
- Prioritizes 15 common business models at top
- Limit 100 models for performance

**Code Reference:**
```javascript
// Lines 227-276
async _getAvailableModels() {
    const result = await this.messaging.rpc({
        model: "ir.model",
        method: "search_read",
        kwargs: {
            domain: [
                ["transient", "=", false],
                ["model", "not in", ["mail.message", "mail.followers", "ir.attachment"]],
                ["access_ids", "!=", false],
            ],
            fields: ["model", "name"],
            order: "name",
            limit: 100,
        },
    });
    // Prioritize common models...
}
```

#### Step 2: Record Search
- Search input with debouncing (300ms)
- Uses `name_search` RPC method
- Shows max 20 results
- Click result → selects for linking

**Code Reference:**
```javascript
// Lines 475-524
async _searchRecords(model, query, resultsContainer, loadingContainer) {
    const result = await this.messaging.rpc({
        model: model,
        method: "name_search",
        kwargs: {
            name: query,
            limit: 20,
        },
    });
    // Render results with click handlers...
}
```

#### Step 3: Modal UI Structure
- Bootstrap modal with 2-step wizard
- Step 1: Model selection dropdown
- Step 2: Search input + results list
- Selected record preview panel
- "Link to Chat" button (disabled until selection)

**Code Reference:**
```javascript
// Lines 310-380 - _createRecordPickerModalHtml()
// Modal HTML with:
// - Model selection dropdown
// - Search input with icon
// - Results container (max-height: 300px, scrollable)
// - Selected record preview alert
// - Cancel/Link buttons in footer
```

### 4. Unlink Record ✅
**16.0 Implementation:**
- Click unlink button → confirmation dialog
- Bootstrap modal with warning icon
- Shows record name in confirmation message
- Explains action won't delete record, only removes link
- Updates thread: `model=False, res_id=False`
- Shows success notification

**Code Reference:**
```javascript
// Lines 206-220
async onClickUnlinkRecord() {
    const confirmed = await this._showUnlinkConfirmationDialog();
    if (!confirmed) return;

    await this.messaging.rpc({
        model: "llm.thread",
        method: "write",
        args: [[this.thread.id], { model: false, res_id: false }],
    });

    // Refresh thread and show notification
}
```

**Confirmation Dialog:**
```javascript
// Lines 605-670 - _showUnlinkConfirmationDialog()
// Modal with:
// - Warning icon
// - Record name display
// - Clear explanation message
// - Cancel/Unlink buttons
```

### 5. Responsive Design ✅
**16.0 Implementation:**
- Desktop: Shows full record name + separate unlink button
- Mobile (`isSmall`): Hides record name text, shows only icon + dropdown for actions
- Button group pattern for clean UI

**Code Reference:**
```xml
<!-- llm_chat_thread_related_record.xml:11-75 -->
<!-- Desktop: Full name displayed -->
<span t-if="!isSmall" class="text-truncate small" style="max-width: 100px;">
    <t t-esc="relatedRecordDisplayName" />
</span>

<!-- Desktop: Separate unlink button -->
<button t-if="!isSmall" class="btn btn-sm btn-outline-danger">
    <i class="fa fa-unlink" />
</button>

<!-- Mobile: Dropdown menu for actions -->
<div t-if="isSmall" class="dropdown">
    <ul class="dropdown-menu dropdown-menu-end">
        <li><a class="dropdown-item" t-on-click="onClickUnlinkRecord">
            <i class="fa fa-unlink me-2 text-warning" />
            Unlink Record
        </a></li>
    </ul>
</div>
```

### 6. Error Handling ✅
**16.0 Implementation:**
- Try-catch blocks around all RPC calls
- Console error logging
- User-friendly notifications via `messaging.notify()`
- Handles: network errors, permission errors, deleted records

**Code Reference:**
```javascript
// Lines 81-97 - Display name loading errors
catch (error) {
    console.error("Error loading related record display name:", error);
    this.state.relatedRecordDisplayName = "";
}

// Lines 135-154 - Open record errors
catch (error) {
    console.error("Error opening related record:", error);
    this.messaging.notify({
        message: this.env._t("Failed to open related record"),
        type: "danger",
    });
}
```

---

## Architecture Migration: 16.0 → 18.0

### Key Framework Changes

| Aspect | 16.0 Pattern | 18.0 Pattern | Impact |
|--------|--------------|--------------|--------|
| **Component Registration** | `registerMessagingComponent()` | Standard OWL component import | High - Complete rewrite |
| **Props** | `{ thread: Object }` (messaging model) | `{ thread: Object }` (plain object) | Low - Same structure |
| **RPC Calls** | `this.messaging.rpc({ model, method, args })` | `this.orm.call(model, method, args)` | Medium - Different API |
| **Notifications** | `this.messaging.notify({ message, type })` | `this.notification.add(message, { type })` | Low - Similar API |
| **Modals** | jQuery Bootstrap modals (`$().modal()`) | Odoo Dialog service | High - Different approach |
| **Action Service** | `this.env.services.action.doAction()` | `this.action.doAction()` | Low - Same API |
| **Device Detection** | `this.messaging.device.isSmall` | `this.ui.isSmall` | Low - Different service |

### Service Dependencies

**16.0:**
```javascript
// Implicit from messaging component
this.messaging  // Provides: rpc, notify, device
this.env.services.action
```

**18.0:**
```javascript
setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.dialog = useService("dialog");
    this.notification = useService("notification");
    this.ui = useService("ui");
}
```

---

## Implementation Plan - 18.0

### Phase 1: Component Structure

**File Structure:**
```
llm_thread/static/src/components/llm_related_record/
├── llm_related_record.js       # 250-300 lines
├── llm_related_record.xml      # 120-150 lines
└── llm_related_record.scss     # 50-80 lines
```

**Component Class Signature:**
```javascript
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class LLMRelatedRecord extends Component {
    static template = "llm_thread.LLMRelatedRecord";
    static props = {
        thread: Object,
    };

    setup() {
        this.state = useState({
            relatedRecordDisplayName: "",
            isLoading: false,
        });

        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.ui = useService("ui");

        onMounted(() => this.loadRelatedRecordDisplayName());
    }
}
```

### Phase 2: Feature Implementation Mapping

#### Feature 1: Display Linked Record
**Migration Steps:**
1. ✅ Convert `this.messaging.rpc()` → `this.orm.call()`
2. ✅ Keep icon mapping dictionary (copy from 16.0)
3. ✅ Update template to use thread.model/thread.res_id (not thread.relatedThreadModel)
4. ✅ Add loading state handling

**New Code:**
```javascript
async loadRelatedRecordDisplayName() {
    if (!this.props.thread.model || !this.props.thread.res_id) {
        this.state.relatedRecordDisplayName = "";
        return;
    }

    try {
        this.state.isLoading = true;
        const result = await this.orm.call(
            this.props.thread.model,
            "name_get",
            [[this.props.thread.res_id]]
        );
        this.state.relatedRecordDisplayName = result[0][1];
    } catch (error) {
        console.error("Error loading display name:", error);
        this.state.relatedRecordDisplayName = "";
    } finally {
        this.state.isLoading = false;
    }
}

getRecordIcon() {
    const iconMap = { /* copy from 16.0 */ };
    return iconMap[this.props.thread.model] || "fa-file-o";
}
```

#### Feature 2: Open Linked Record
**Migration Steps:**
1. ✅ Keep `action.doAction()` call (same API)
2. ✅ Update notification service

**New Code:**
```javascript
async openRelatedRecord() {
    if (!this.props.thread.model || !this.props.thread.res_id) {
        return;
    }

    try {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.thread.model,
            res_id: this.props.thread.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    } catch (error) {
        console.error("Error opening record:", error);
        this.notification.add(
            this.env._t("Failed to open related record"),
            { type: "danger" }
        );
    }
}
```

#### Feature 3: Link New Record (Record Picker)
**Migration Steps:**
1. ✅ Replace jQuery Bootstrap modal → Odoo Dialog service
2. ✅ Create separate `RecordPickerDialog` component
3. ✅ Convert RPC calls to `orm.searchRead()` and `orm.call()`
4. ✅ Keep 2-step wizard logic

**New Code Structure:**
```javascript
// In llm_related_record.js
openRecordPicker() {
    this.dialog.add(RecordPickerDialog, {
        onConfirm: async (model, recordId) => {
            await this.linkRecord(model, recordId);
        },
    });
}

async linkRecord(model, recordId) {
    try {
        await this.orm.write(
            "llm.thread",
            [this.props.thread.id],
            { model: model, res_id: recordId }
        );

        // Reload thread data
        await this.loadRelatedRecordDisplayName();

        this.notification.add(
            this.env._t("Record linked successfully"),
            { type: "success" }
        );
    } catch (error) {
        console.error("Error linking record:", error);
        this.notification.add(
            this.env._t("Failed to link record"),
            { type: "danger" }
        );
    }
}

// Separate file: llm_record_picker_dialog.js
import { Dialog } from "@web/core/dialog/dialog";

export class RecordPickerDialog extends Component {
    static template = "llm_thread.RecordPickerDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.state = useState({
            selectedModel: "",
            searchQuery: "",
            searchResults: [],
            selectedRecord: null,
        });

        this.orm = useService("orm");
    }

    async loadAvailableModels() {
        return await this.orm.searchRead(
            "ir.model",
            [
                ["transient", "=", false],
                ["model", "not in", ["mail.message", "mail.followers", "ir.attachment"]],
                ["access_ids", "!=", false],
            ],
            ["model", "name"],
            { limit: 100, order: "name" }
        );
    }

    async searchRecords(query) {
        if (!this.state.selectedModel || query.length < 2) return;

        const results = await this.orm.call(
            this.state.selectedModel,
            "name_search",
            [query],
            { limit: 20 }
        );

        this.state.searchResults = results.map(([id, name]) => ({
            id,
            name,
            model: this.state.selectedModel,
        }));
    }

    confirm() {
        if (this.state.selectedRecord) {
            this.props.onConfirm(
                this.state.selectedRecord.model,
                this.state.selectedRecord.id
            );
            this.props.close();
        }
    }
}
```

#### Feature 4: Unlink Record
**Migration Steps:**
1. ✅ Replace jQuery Bootstrap modal → Odoo ConfirmationDialog
2. ✅ Convert write RPC call to `orm.write()`
3. ✅ Update notification service

**New Code:**
```javascript
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

async unlinkRecord() {
    if (!this.props.thread.model || !this.props.thread.res_id) {
        return;
    }

    const recordName = this.state.relatedRecordDisplayName ||
        `${this.props.thread.model} #${this.props.thread.res_id}`;

    this.dialog.add(ConfirmationDialog, {
        title: this.env._t("Unlink Record"),
        body: this.env._t(
            "Are you sure you want to unlink %s from this chat? " +
            "This won't delete the record, only remove the link.",
            recordName
        ),
        confirm: async () => {
            try {
                await this.orm.write(
                    "llm.thread",
                    [this.props.thread.id],
                    { model: false, res_id: false }
                );

                // Update local state
                this.state.relatedRecordDisplayName = "";

                this.notification.add(
                    this.env._t("Record unlinked successfully"),
                    { type: "success" }
                );
            } catch (error) {
                console.error("Error unlinking record:", error);
                this.notification.add(
                    this.env._t("Failed to unlink record"),
                    { type: "danger" }
                );
            }
        },
        cancel: () => {},
    });
}
```

#### Feature 5: Responsive Design
**Migration Steps:**
1. ✅ Replace `this.messaging.device.isSmall` → `this.ui.isSmall`
2. ✅ Keep same template structure with `t-if="!ui.isSmall"`

**Template:**
```xml
<t t-name="llm_thread.LLMRelatedRecord">
    <div t-if="props.thread.model and props.thread.res_id">
        <div class="btn-group">
            <!-- Open Record Button -->
            <button class="btn btn-sm btn-outline-secondary"
                    t-on-click="openRelatedRecord"
                    t-att-disabled="state.isLoading">
                <i t-attf-class="fa {{ getRecordIcon() }}" />
                <span t-if="!ui.isSmall" t-esc="state.relatedRecordDisplayName" />
            </button>

            <!-- Unlink Button (Desktop) -->
            <button t-if="!ui.isSmall"
                    class="btn btn-sm btn-outline-danger"
                    t-on-click="unlinkRecord">
                <i class="fa fa-unlink" />
            </button>

            <!-- Mobile Dropdown -->
            <Dropdown t-if="ui.isSmall">
                <button class="btn btn-sm btn-outline-secondary dropdown-toggle-split">
                    <i class="fa fa-caret-down" />
                </button>
                <t t-set-slot="content">
                    <DropdownItem onSelected="unlinkRecord">
                        <i class="fa fa-unlink me-2 text-warning" />
                        Unlink Record
                    </DropdownItem>
                </t>
            </Dropdown>
        </div>
    </div>

    <!-- No Record Linked -->
    <div t-else="">
        <button class="btn btn-sm btn-outline-secondary"
                t-on-click="openRecordPicker"
                title="Link to a record">
            <i class="fa fa-plus" />
            <span t-if="!ui.isSmall">Link</span>
        </button>
    </div>
</t>
```

### Phase 3: Integration

**Thread Header Integration:**
```xml
<!-- In llm_thread_header.xml, after thread name editing section -->
<div class="flex-grow-1 d-flex align-items-center me-3">
    <!-- Thread name editing section -->
    ...
</div>

<!-- Add Related Record Component -->
<div class="me-2 flex-shrink-0">
    <LLMRelatedRecord thread="activeThread" />
</div>

<!-- Existing dropdowns section -->
<div class="d-flex align-items-center gap-2">
    <!-- Provider, Model, Tools dropdowns -->
    ...
</div>
```

**Import in Thread Header JS:**
```javascript
// In llm_thread_header.js
import { LLMRelatedRecord } from "../llm_related_record/llm_related_record";

export class LLMThreadHeader extends Component {
    static components = {
        ...
        LLMRelatedRecord,
    };
}
```

---

## Verification Checklist

### Functionality Verification (16.0 Baseline)

#### ✅ Display Features
- [ ] Shows linked record display name
- [ ] Shows model-specific icon (15+ models supported)
- [ ] Shows loading spinner while fetching name
- [ ] Shows "Link" button when no record linked
- [ ] Desktop: Shows full record name
- [ ] Mobile: Hides record name, shows icon only

#### ✅ Open Record
- [ ] Click record name opens form view
- [ ] Opens in current window (target: "current")
- [ ] Shows error notification if fails
- [ ] Logs error to console

#### ✅ Link Record (Record Picker)
- [ ] Opens modal dialog with 2-step wizard
- [ ] Step 1: Shows model selection dropdown
- [ ] Step 1: Loads up to 100 models
- [ ] Step 1: Prioritizes 15 common business models
- [ ] Step 1: Excludes transient and mail models
- [ ] Step 2: Shows search input
- [ ] Step 2: Search has 300ms debounce
- [ ] Step 2: Uses `name_search` method
- [ ] Step 2: Shows max 20 results
- [ ] Step 2: Minimum 2 characters to search
- [ ] Shows selected record preview
- [ ] "Link" button disabled until record selected
- [ ] Links record on confirm
- [ ] Refreshes display name after link
- [ ] Shows success notification
- [ ] Handles errors with notification

#### ✅ Unlink Record
- [ ] Shows confirmation dialog
- [ ] Dialog shows record name
- [ ] Dialog has warning icon
- [ ] Dialog explains action won't delete record
- [ ] Unlinks on confirm (model=false, res_id=false)
- [ ] Updates UI immediately
- [ ] Shows success notification
- [ ] Handles errors with notification

#### ✅ Error Handling
- [ ] Network errors show notification
- [ ] Permission errors show notification
- [ ] Deleted records handled gracefully
- [ ] All errors logged to console
- [ ] No crashes on invalid data

#### ✅ Responsive Design
- [ ] Desktop: Full layout with all text
- [ ] Mobile: Compact layout with icons
- [ ] Mobile: Dropdown menu for actions
- [ ] Buttons properly sized (32px height)
- [ ] Text truncation with max-width
- [ ] Proper spacing and alignment

### Code Quality Verification

#### ✅ Architecture (Odoo 18.0)
- [ ] Uses standard OWL Component (not messaging component)
- [ ] No deprecated `registerMessagingComponent()`
- [ ] Uses `useService()` hooks
- [ ] Services: orm, action, dialog, notification, ui
- [ ] No jQuery dependencies
- [ ] No Bootstrap modal JavaScript
- [ ] Uses Odoo Dialog service
- [ ] Uses ConfirmationDialog for confirms

#### ✅ Performance
- [ ] Debounced search (300ms)
- [ ] Reasonable limits (20 results, 100 models)
- [ ] No unnecessary re-renders
- [ ] Efficient state management
- [ ] Proper loading states

#### ✅ Maintainability
- [ ] Clear method names
- [ ] Proper error messages
- [ ] Console logging for debugging
- [ ] Clean separation of concerns
- [ ] Reusable components (RecordPickerDialog)
- [ ] Well-commented code

---

## Testing Strategy

### Unit Tests
```python
# tests/test_llm_thread_related_record.py

def test_link_record_to_thread(self):
    """Test linking a partner to a thread"""
    thread = self.env['llm.thread'].create({'name': 'Test'})
    partner = self.env['res.partner'].create({'name': 'John Doe'})

    thread.write({
        'model': 'res.partner',
        'res_id': partner.id,
    })

    self.assertEqual(thread.model, 'res.partner')
    self.assertEqual(thread.res_id, partner.id)

def test_unlink_record_from_thread(self):
    """Test unlinking a record"""
    thread = self.env['llm.thread'].create({
        'name': 'Test',
        'model': 'res.partner',
        'res_id': 1,
    })

    thread.write({
        'model': False,
        'res_id': False,
    })

    self.assertFalse(thread.model)
    self.assertFalse(thread.res_id)

def test_related_record_proxy(self):
    """Test RelatedRecordProxy class"""
    partner = self.env['res.partner'].create({'name': 'Jane Doe'})
    thread = self.env['llm.thread'].create({
        'name': 'Test',
        'model': 'res.partner',
        'res_id': partner.id,
    })

    # Test proxy usage (from prepend_messages context)
    # This would be tested via message generation
```

### Integration Tests (Manual)

#### Test Case 1: Full Link Workflow
```
Steps:
1. Create new chat thread
2. Click "+" link button
3. Select "Contact / Customer" from dropdown
4. Search for "John"
5. Select "John Doe" from results
6. Click "Link to Chat"
7. Verify record name appears in header
8. Click record name
9. Verify partner form opens

Expected:
- All steps work smoothly
- Record picker modal closes after link
- Success notification appears
- Record name displays correctly
- Form view opens with correct record
```

#### Test Case 2: Unlink Workflow
```
Steps:
1. Open thread with linked record
2. Click unlink button
3. Read confirmation message
4. Click "Unlink Record"
5. Verify record removed from header
6. Verify "+" button appears

Expected:
- Confirmation dialog shows record name
- Dialog explains action
- Unlink succeeds
- UI updates immediately
- Success notification appears
```

#### Test Case 3: Error Handling
```
Steps:
1. Link a record to thread
2. Delete the linked record via another window
3. Refresh thread
4. Click to open record (should fail gracefully)

Expected:
- No JavaScript errors
- Error notification appears
- Component doesn't crash
```

#### Test Case 4: Responsive Design
```
Steps:
1. Open thread with linked record (desktop)
2. Verify full layout
3. Resize window to mobile width
4. Verify compact layout
5. Verify dropdown appears
6. Click dropdown → unlink

Expected:
- Smooth responsive transition
- Mobile layout shows only icon
- Dropdown menu works
- All actions still functional
```

### Browser Compatibility
- [ ] Chrome 120+
- [ ] Firefox 120+
- [ ] Safari 17+
- [ ] Edge 120+

---

## Migration Checklist

### Pre-Implementation
- [x] Document 16.0 baseline features
- [x] Identify architectural changes needed
- [x] Create implementation plan
- [ ] Review plan with team

### Implementation
- [ ] Create component file structure
- [ ] Implement LLMRelatedRecord component (JS)
- [ ] Create component template (XML)
- [ ] Add component styling (SCSS)
- [ ] Implement RecordPickerDialog component
- [ ] Create record picker template
- [ ] Integrate into Thread Header
- [ ] Update imports and manifests

### Testing
- [ ] Manual testing: Display linked record
- [ ] Manual testing: Open record
- [ ] Manual testing: Link record (full workflow)
- [ ] Manual testing: Unlink record
- [ ] Manual testing: Responsive design
- [ ] Manual testing: Error scenarios
- [ ] Unit tests: Backend fields
- [ ] Integration tests: Full workflows
- [ ] Browser compatibility testing

### Documentation
- [ ] Update llm_thread README
- [ ] Add code comments
- [ ] Update CLAUDE.md migration status
- [ ] Add to changelog

### Deployment
- [ ] Code review
- [ ] Merge to migration branch
- [ ] Deploy to test environment
- [ ] User acceptance testing
- [ ] Deploy to production

---

## Timeline Estimate

| Phase | Estimated Time | Status |
|-------|---------------|--------|
| Component Implementation | 2 hours | ⏳ Pending |
| Template & Styling | 1 hour | ⏳ Pending |
| Record Picker Dialog | 1.5 hours | ⏳ Pending |
| Integration & Testing | 1.5 hours | ⏳ Pending |
| Documentation | 0.5 hours | ⏳ Pending |
| **Total** | **6.5 hours** | ⏳ Pending |

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Dialog service API different than expected | Medium | Low | Review Odoo 18 Dialog documentation first |
| Performance issues with large model lists | Low | Low | Already has 100 model limit |
| Responsive design issues | Low | Low | Copy proven 16.0 patterns |
| Name search fails for some models | Medium | Low | Fallback to search_read if name_search unavailable |
| Thread update doesn't refresh UI | Medium | Low | Use llmStore refresh pattern from existing code |

---

## Success Criteria

✅ **Component is considered complete when:**

1. All 16.0 features work identically in 18.0
2. All verification checklist items pass
3. No console errors or warnings
4. Responsive design works on mobile and desktop
5. Error handling provides clear user feedback
6. Code follows Odoo 18.0 patterns (no deprecated APIs)
7. Performance is acceptable (no lag, smooth interactions)
8. Documentation is updated

---

## References

### Source Code (16.0)
- Component: `llm_thread/static/src/components/llm_chat_thread_related_record/`
- Integration: `llm_thread/static/src/components/llm_chat_thread_header/llm_chat_thread_header.xml:7-9`
- Backend: `llm_thread/models/llm_thread.py:15-92, 127-134`

### Odoo 18.0 Documentation
- Dialog Service: https://www.odoo.com/documentation/18.0/developer/reference/frontend/services.html#dialog-service
- ORM Service: https://www.odoo.com/documentation/18.0/developer/reference/frontend/services.html#orm-service
- OWL Components: https://www.odoo.com/documentation/18.0/developer/reference/frontend/owl_components.html

### Related Documents
- `CLAUDE.md` - Project migration documentation
- `MIGRATION_16_TO_18.md` - General migration guide
- `LLM_THREAD_18_MIGRATION_GUIDE.md` - LLM thread specific migration

---

**Document Version:** 1.0
**Created:** 2025-10-23
**Last Updated:** 2025-10-23
**Status:** Ready for Review

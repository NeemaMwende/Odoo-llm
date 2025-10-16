# Odoo LLM Integration Modules - Project Context

## Project Overview

This is a comprehensive suite of Odoo modules for integrating Large Language Models (LLMs) with Odoo ERP. The modules provide AI-powered features, knowledge management, and various LLM provider integrations.

## Current Status

- **Current Version**: Odoo 16.0
- **Target Version**: Odoo 18.0
- **Migration Status**: In Progress
- **Main Branch**: 16.0
- **Migration Branch**: 18.0-migration

## Module Architecture

### Core Modules

1. **llm** - Base module providing core LLM functionality, models, and providers
2. **llm_thread** - Thread management for LLM conversations
3. **llm_tool** - Tool management and consent configuration for LLM operations
4. **llm_assistant** - Assistant functionality with prompts, categories, and tags

### Provider Modules

- **llm_anthropic** - Anthropic Claude integration
- **llm_openai** - OpenAI GPT integration
- **llm_mistral** - Mistral AI integration
- **llm_ollama** - Ollama local LLM integration
- **llm_litellm** - LiteLLM proxy integration
- **llm_replicate** - Replicate API integration
- **llm_fal_ai** - Fal.ai integration

### Knowledge Management

- **llm_knowledge** - Core knowledge base with chunking and RAG
- **llm_knowledge_automation** - Automated knowledge collection
- **llm_knowledge_llama** - Llama-specific knowledge features
- **llm_knowledge_mistral** - Mistral-specific knowledge features
- **llm_tool_knowledge** - Tool-knowledge integration

### Vector Storage

- **llm_pgvector** - PostgreSQL vector storage
- **llm_chroma** - Chroma vector database integration
- **llm_qdrant** - Qdrant vector database integration

### Generation & Processing

- **llm_generate** - Content generation features
- **llm_generate_job** - Job queue for generation tasks
- **llm_training** - Training dataset management
- **llm_comfyui** - ComfyUI integration
- **llm_comfy_icu** - ComfyICU integration

### Additional Features

- **llm_document_page** - Document page integration
- **llm_mcp** - Model Context Protocol server
- **llm_store** - LLM marketplace/store functionality
- **web_json_editor** - JSON editor widget

## Migration to Odoo 18.0 - Key Changes

### Critical Breaking Changes

1. **tree → list**: All `<tree>` tags must be renamed to `<list>`
2. **attrs → direct attributes**: Convert domain syntax to Python expressions
3. **states → invisible**: Button states attribute replaced with invisible
4. **name_get() → \_compute_display_name()**: Display name computation changed
5. **message_format() removed**: Use Store system with `_to_store()` method instead
6. **Registry import**: Use `from odoo.modules.registry import Registry` not `from odoo import registry`

### Module-Specific Migration Requirements

#### High Priority (Core + Heavy UI)

- **llm**: Update manifest, migrate views (4 view files)
- **llm_thread**: Migrate tree views in thread views
- **llm_tool**: Migrate consent config and tool views
- **llm_assistant**: Multiple view files with tree tags
- **llm_knowledge**: Complex module with multiple views and wizards

#### Medium Priority (Feature Modules)

- **llm_mcp**: Has attrs attributes that need conversion
- **llm_training**: Dataset and job views need migration
- **llm_generate_job**: Queue and job views
- **llm_pgvector**: Embedding views
- **llm_store**: Store views
- **llm_document_page**: Wizard attrs attributes
- **llm_litellm**: Provider views with attrs

#### Low Priority (Manifest Only)

Provider modules with minimal UI:

- llm_anthropic, llm_openai, llm_mistral, llm_ollama
- llm_replicate, llm_fal_ai, llm_comfy_icu, llm_comfyui
- llm_generate, llm_chroma, llm_qdrant
- llm_knowledge_llama, llm_knowledge_mistral, llm_tool_knowledge

## Testing Strategy

1. Run individual module tests after each migration
2. Test inter-module dependencies
3. Validate all view rendering
4. Check all workflows and actions
5. Verify API compatibility

## Code Quality Standards

- Python 3.11+ compatibility
- Ruff for linting and formatting
- Pre-commit hooks configured
- Type hints where applicable

## Development Commands

### Testing

```bash
# Run all tests
./run_tests.sh

# Test specific module
odoo-bin --test-enable --stop-after-init --test-tags=llm -d test_db -u llm
```

### Code Quality

```bash
# Format and lint
ruff format . && ruff check . --fix --unsafe-fixes

# Pre-commit
pre-commit run --all-files
```

### Cherry-Picking Modules from Migration Branch

When you need to restore already-migrated modules from `18.0-migration` to the current working branch:

```bash
# 1. Check what exists in the migration branch
git show 18.0-migration:llm_module_name

# 2. Cherry-pick entire module directory
git checkout 18.0-migration -- llm_module_name

# 3. Stage and commit
git add llm_module_name
git commit -m "chore: restore llm_module_name from 18.0-migration branch"
```

**Example:**
```bash
# Restore llm_comfyui and llm_comfy_icu
git checkout 18.0-migration -- llm_comfyui
git checkout 18.0-migration -- llm_comfy_icu
git add llm_comfyui llm_comfy_icu
git commit -m "chore: restore image generation modules from 18.0-migration"
```

**Note:** This brings the module as it exists in `18.0-migration` without bringing uncommitted changes from that branch.

## Migration Progress Tracking

### ✅ Completed (18.0 Compatible)

#### Core Modules - COMPLETED ✅

1. **llm** - Base module providing core LLM functionality, models, and providers

   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies
   - ✅ Core LLM provider and model management

2. **llm_thread** - Thread management for LLM conversations

   - ✅ Migrated to Odoo 18.0 mail system architecture
   - ✅ Implemented proper `_init_messaging()` and `_thread_to_store()` methods
   - ✅ Fixed message handling (tool messages, empty message filtering, squashing)
   - ✅ Fixed HTML escaping issues in streaming messages
   - ✅ Updated thread header components with proper fetchData() patterns
   - ✅ Integrated with standard mail.store service patterns

3. **llm_tool** - Tool management and consent configuration for LLM operations

   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and tool configuration views
   - ✅ Tool consent and management functionality

4. **llm_assistant** - Assistant functionality with prompts and tools
   - ✅ Migrated assistant dropdown UI with full functionality
   - ✅ Implemented assistant selection and clearing
   - ✅ Fixed UI reactivity issues with proper context binding
   - ✅ Extended `_thread_to_store()` to handle assistant_id states
   - ✅ Clean separation from llm_thread module following DRY principles

#### Text/Chat Provider Modules - COMPLETED ✅

1. **llm_openai** - OpenAI GPT integration
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

2. **llm_mistral** - Mistral AI integration
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

3. **llm_ollama** - Ollama local LLM integration
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

#### Image Generation Providers - COMPLETED ✅

1. **llm_replicate** - Replicate API integration (image generation)
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies
   - ⚠️ Known issue: API predictions auto-delete after 1 hour (TODO documented)

2. **llm_comfyui** - ComfyUI integration (image workflows)
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

3. **llm_comfy_icu** - ComfyICU integration
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

#### Generation & Content Modules - COMPLETED ✅

1. **llm_generate** - Content generation features
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies
   - ✅ Media form with JSON editor integration
   - ✅ Collapsible body_json display for debugging

2. **llm_training** - Training dataset management
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

#### Integration Modules - COMPLETED ✅

1. **llm_mcp_server** - Model Context Protocol server (MCP)
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

2. **llm_letta** - Letta SDK integration
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies

#### Utility Modules - COMPLETED ✅

1. **web_json_editor** - JSON editor widget
   - ✅ Migrated to Odoo 18.0
   - ✅ Updated manifests and dependencies
   - ✅ Used in llm_generate for generation parameter editing

### 🚧 Recent Improvements (Latest Session)

#### Bug Fixes & Architecture Cleanup

- ✅ **Dead Code Cleanup**: Removed unused frontend model system (llm_assistant/static/src/models/, components/llm_chat_thread_header/)
- ✅ **RPC Architecture**: Refactored assistant selection to use controller endpoint instead of direct ORM calls
- ✅ **System Prompt Verification**: Confirmed prepend_messages correctly passes system prompts to LLM providers
- ✅ **Reactivity Fixes**: Fixed assistant clearing, schema source indicator, and button state reactivity issues
- ✅ **Jump-to-Present Button**: Fixed scroll direction for LLM threads by passing correct scrollRef to Thread component
- ✅ **Body JSON Display**: Added collapsible UI for generation input/output data in user and assistant messages
- ✅ **UI Alignment**: Fixed vertical alignment of schema source badge with text

#### Technical Debt Identified

- 📝 TODO: Fix Replicate file expiration (API predictions deleted after 1 hour) - implement provider hook pattern for downloading outputs
- 📝 TODO: Fix misleading variable naming (output_data contains input metadata, not actual output)

#### Documentation Updates

- 📚 Added Odoo 18 frontend model system changes to CLAUDE.md (registerModel removal, Record-based pattern)
- 📚 Documented correct RPC import pattern (`import { rpc }` as standalone function)

### 🚧 In Progress

#### UI/UX Improvements

- 🔄 Make LLM components responsive/mobile friendly

### ⏳ Remaining Migration Tasks (Not in Current Branch)

#### High Priority (Image Generation Providers)

- **llm_fal_ai** - Fal.ai integration (image generation)

#### Medium Priority (Knowledge & Advanced Features)

- **llm_knowledge** - Knowledge base with chunking and RAG
- **llm_knowledge_automation** - Automated knowledge collection
- **llm_generate_job** - Job queue for generation tasks

#### Low Priority (Vector Storage & Extensions)

- **llm_pgvector**, **llm_chroma**, **llm_qdrant** - Vector database integrations
- **llm_document_page** - Document page integration
- **llm_store** - LLM marketplace functionality
- **llm_anthropic** - Anthropic Claude integration (needs to be re-added)
- **llm_litellm** - LiteLLM proxy integration (needs to be re-added)

## Future Architecture Improvements

### \_to_store Pattern Implementation

**Priority**: Medium
**Investigation needed**: Study how Odoo's mail module implements `_to_store()` methods for different models.

**Potential Implementation**:

- **llm.provider** - Standardize provider data serialization for frontend
- **llm.model** - Consistent model data structure in mail.store
- **llm.tool** - Tool data formatting for UI components
- **llm.assistant** - Enhanced assistant data structure (already partially implemented)

**Benefits**:

- Consistent data format across all LLM models
- Better integration with Odoo 18.0 mail.store patterns
- Simplified frontend data access and reactivity
- Reduced custom serialization logic

**Research Tasks**:

1. Analyze `mail.thread._to_store()` and related methods
2. Study how different mail models extend the pattern
3. Design unified approach for LLM model serialization
4. Create base mixin for LLM models to inherit

## Known Issues

- Some modules may have additional hidden dependencies
- Vector storage modules might need special attention for data migration
- Job queue modules need careful testing for async operations

## Odoo 18.0 Mail System Architecture (IMPORTANT)

### Major Frontend Model System Changes

**CRITICAL: Odoo 18 completely replaced the frontend model system!**

#### Odoo 16 Pattern (REMOVED in 18.0):
```javascript
// ❌ DON'T USE - This doesn't exist in Odoo 18!
import { registerModel } from '@mail/model/model_core';
import { registerPatch } from '@mail/model/model_core';

registerModel({
    name: 'Thread',
    fields: {
        id: attr(),
        name: attr(),
    },
    recordMethods: {
        async doSomething() { ... }
    }
});

registerPatch({
    name: 'Thread',
    fields: {
        customField: attr(),
    }
});
```

#### Odoo 18 Pattern (NEW - Use This):
```javascript
// ✅ USE - ES6 classes extending Record
import { Record } from "@mail/core/common/record";
import { patch } from "@web/core/utils/patch";

// Define model as ES6 class
export class Thread extends Record {
    static id = AND("model", "id");
    static records = {};

    // Properties as class fields
    id;
    model;
    name;

    // Methods as class methods
    async doSomething() { ... }
}

// Patch using standard OWL patch()
patch(Thread.prototype, {
    customField = undefined;

    async doCustomThing() { ... }
});
```

#### Key Architectural Changes:

1. **No `registerModel()`** - Models are ES6 classes extending `Record`
2. **No `registerPatch()`** - Use OWL's `patch()` utility
3. **Records in `static records`** - Centralized record storage
4. **OWL reactivity** - Built-in reactive system via `@odoo/owl`
5. **Type-safe** - Better JSDoc/TypeScript support
6. **Auto-registration** - Via `modelRegistry` instead of explicit calls

#### RPC Calls in Services:

```javascript
// ✅ Import rpc as standalone function
import { rpc } from "@web/core/network/rpc";

// Use directly (NOT via env.services.rpc)
const result = await rpc("/my/endpoint", { param: value });
```

### Mail Store System

- **USE** `mail.store` service for all message/thread operations
- **REUSE** existing mail components, don't create separate messaging models
- **PATCH** components conditionally using `@web/core/utils/patch`
- The new system uses Record-based reactive architecture

### Thread and Message Management

```javascript
// Correct Thread.get() format in Odoo 18.0
mailStore.Thread.get({ model: "llm.thread", id: threadId });

// Message insertion pattern
mailStore.insert({ "mail.message": [messageData] }, { html: true });

// IMPORTANT: Also add to thread.messages collection for UI updates
if (!thread.messages.some((m) => m.id === message.id)) {
  thread.messages.push(message);
}
```

### Message Serialization

```python
# Use Store system for message formatting
from odoo.addons.mail.tools.discuss import Store

def to_store_format(self, message):
    store = Store()
    message._to_store(store)
    result = store.get_result()
    return result['mail.message'][0]
```

### LLM-Specific Implementation

#### Service Setup

```javascript
export const llmStoreService = {
  dependencies: ["orm", "bus_service", "mail.store", "notification"],
  start(env, { orm, bus_service, "mail.store": mailStore, notification }) {
    // mailStore is the standard Odoo mail.store service
  },
};
```

#### Safe Component Patching

```javascript
patch(Composer.prototype, {
  setup() {
    super.setup();
    try {
      this.llmStore = useService("llm.store");
    } catch (error) {
      this.llmStore = null; // Graceful fallback
    }
  },
});
```

#### Message Processing Rules

- **User messages**: Plain text, no processing through `_process_llm_body()`
- **Assistant messages**: Process through `_process_llm_body()` for markdown→HTML
- **Tool messages**: Use `body_json` field, no HTML processing

#### Streaming Architecture

1. User message → `message_post()` → standard bus events
2. AI response → EventSource streaming → custom handling in llm.store
3. Messages inserted via `mailStore.insert()`
4. Manually add to `thread.messages` collection for reactivity

### Message History Flow for LLM

1. User message posted with `llm_role="user"` → saved to DB
2. `generate_messages()` called → `get_llm_messages()` retrieves all messages
3. Full history including new user message passed to LLM

### Common Pitfalls to Avoid

- Don't use `message_format()` - it's removed in 18.0
- Don't use `existingMessage.update()` for streaming - use `mailStore.insert()`
- Don't forget to add messages to `thread.messages` collection
- Don't process user messages as markdown/HTML
- Don't use wrong Thread.get() format (array instead of object)

## References

- [MIGRATION_16_TO_18.md](./MIGRATION_16_TO_18.md) - Detailed migration guide
- [LLM_THREAD_18_MIGRATION_GUIDE.md](./LLM_THREAD_18_MIGRATION_GUIDE.md) - LLM thread specific migration
- Odoo 18.0 official documentation
- Module interdependency graph (to be created)

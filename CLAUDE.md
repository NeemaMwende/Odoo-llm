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
4. **name_get() → _compute_display_name()**: Display name computation changed
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

## Migration Progress Tracking
See TodoWrite tool for detailed task list. Main categories:
1. Core module migrations (critical path)
2. UI-heavy modules (tree→list, attrs conversion)
3. Provider modules (mostly manifest updates)
4. Testing and validation
5. Documentation updates

## Known Issues
- Some modules may have additional hidden dependencies
- Vector storage modules might need special attention for data migration
- Job queue modules need careful testing for async operations

## Odoo 18.0 Mail System Architecture (IMPORTANT)

### Mail Store System
- **USE** `mail.store` service for all message/thread operations
- **REUSE** existing mail components, don't create separate messaging models
- **PATCH** components conditionally using `@web/core/utils/patch`
- The new system uses Record-based reactive architecture

### Thread and Message Management
```javascript
// Correct Thread.get() format in Odoo 18.0
mailStore.Thread.get({ model: 'llm.thread', id: threadId })

// Message insertion pattern
mailStore.insert({ 'mail.message': [messageData] }, { html: true });

// IMPORTANT: Also add to thread.messages collection for UI updates
if (!thread.messages.some(m => m.id === message.id)) {
    thread.messages.push(message);
}
```

### Message Serialization
```python
# Use Store system for message formatting
from odoo.addons.mail.tools.discuss import Store

def _message_to_store_format(self, message):
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
    }
}
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
    }
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
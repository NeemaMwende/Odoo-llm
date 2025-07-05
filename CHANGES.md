# Changelog

All notable changes to this project will be documented in this file.

## [16.0-pr] - 2025-01-04 - Major Architecture Consolidation

### **Major Architectural Changes**
- **Merged `llm_prompt` module into `llm_assistant`** - Consolidated prompt template functionality with assistant management
- **Eliminated `llm_mail_message_subtypes` module** - Moved message subtypes directly into the base `llm` module
- **Refactored message role handling** - Added stored `llm_role` field to `mail.message` for improved performance

### **Performance Improvements**
- **Database optimization** - Added indexed `llm_role` field for faster message queries
- **Reduced module dependencies** - Streamlined architecture by consolidating related functionality
- **Optimized frontend** - Direct field access instead of computed properties for role checking

### **Message System Overhaul**
- **New `body_json` field** - Structured data storage for tool messages and generation inputs
- **Simplified message posting** - Clean `llm_role` parameter instead of complex subtype handling
- **Enhanced tool execution** - Tool data now stored in `body_json` with better error handling

### **Generation System Improvements**
- **Unified `generate()` API** - Consistent content generation across different model types
- **PostgreSQL advisory locking** - Prevents concurrent generation issues with proper database locks
- **Better streaming support** - Improved real-time message updates during generation

### **Module Version Updates**
- `llm`: 16.0.1.3.0 (added message subtypes and role optimization)
- `llm_assistant`: 16.0.1.4.0 (integrated prompt templates, enhanced testing)
- `llm_thread`: 16.0.1.3.0 (role field optimization, PostgreSQL locking)
- `llm_tool`: 16.0.3.0.0 (body_json refactoring, enhanced execution)
- `llm_generate`: 16.0.2.0.0 (simplified generation API, clean integration)
- `llm_fal_ai`: 16.0.2.0.0 (unified generate endpoint, schema storage)

### **LLM Assistant Module Enhancements**
- **Integrated prompt templates** - Full prompt management within assistant module
- **Enhanced testing wizard** - Better prompt testing with context simulation
- **Improved UI integration** - Streamlined chat interface with assistant and prompt selection

### **Tool System Refactoring**
- **Simplified tool message format** - All tool data in `body_json` instead of separate fields
- **Better error handling** - Enhanced tool execution with proper error propagation
- **Cleaner provider integration** - Unified tool call handling across different LLM providers

### **Migration & Compatibility**
- **Comprehensive migration scripts** - Handles conversion of existing message subtypes and tool data
- **Backward compatibility** - Maintains support for existing workflows during transition
- **Data preservation** - Ensures no loss of existing messages and tool execution history

### **Developer Experience**
- **Cleaner APIs** - Simplified method signatures and reduced complexity
- **Better documentation** - Enhanced README files with usage examples
- **Improved debugging** - Better logging and error messages throughout the system

## Previous Releases

### llm_thread
- **16.0.1.2.0** (2025-01-04) - LLM base module message subtypes integration
- **16.0.1.1.1** (2025-04-09) - Method name consistency updates
- **16.0.1.1.0** (2025-03-06) - Tool integration in chat interface
- **16.0.1.0.0** (2025-01-02) - Initial release

### llm_tool
- **16.0.1.0.1** (2025-04-08) - Minor fixes and improvements
- **16.0.1.0.0** (2025-01-02) - Initial release

### Provider Modules
- **llm_ollama**: 16.0.1.1.0 (2025-03-06) - Chat method parameter updates
- **llm_openai**: 16.0.1.1.3 - OpenAI integration improvements
- **llm_anthropic**: 16.0.1.1.0 - Anthropic provider enhancements
- **llm_litellm**: 16.0.1.1.0 (2025-03-06) - LiteLLM integration updates
- **llm_replicate**: 16.0.1.1.0 (2025-03-06) - Replicate provider improvements

---

*This changelog follows the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.*

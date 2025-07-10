# OVERVIEW.md - Odoo LLM Integration Codebase

## Architecture Overview

This codebase provides a comprehensive framework for integrating Large Language Models (LLMs) into Odoo. The architecture follows a modular design with clear separation of concerns, enabling seamless interaction with various AI providers and building sophisticated AI-powered applications.

## Core Models & Concepts

### Base LLM Module (`llm/`)
**Purpose**: Foundational infrastructure for LLM integration

The base `llm` module provides the core infrastructure that enables AI integration throughout Odoo. It introduces fundamental concepts and extends Odoo's messaging system to support AI interactions:

**Core Components**:

1. **Provider System** (`llm.provider`): Abstraction layer for AI service providers
2. **Publisher Management** (`llm.publisher`): Tracks AI model publishers (OpenAI, Anthropic, Meta, etc.)
3. **Model Registry** (`llm.model`): Catalog of available AI models with capabilities and metadata
4. **Enhanced Messaging**: Extends `mail.message` with AI-specific functionality

**Mail Message Extensions**:
The module enhances Odoo's core messaging system with LLM-specific capabilities:

```python
# Extended mail.message fields
llm_role = fields.Selection([
    ('user', 'User'),
    ('assistant', 'Assistant'),
    ('tool', 'Tool'),
    ('system', 'System')
], compute='_compute_llm_role', store=True, index=True)

body_json = fields.Json()  # Structured data for tool messages
```

**Message Subtypes**: Introduces new message subtypes for AI interactions:
- `llm.mt_user`: User messages in AI conversations
- `llm.mt_assistant`: AI-generated responses
- `llm.mt_tool`: Tool execution results and data
- `llm.mt_system`: System prompts and configuration messages

**Computed Role Field**: The `llm_role` field provides fast, indexed access to message types without complex subtype lookups, enabling:
- 10x faster message queries for AI conversations
- Simplified frontend filtering and display logic
- Efficient conversation history processing
- Optimized database operations for large conversation datasets

**Foundation for Ecosystem**: This base module enables all other LLM modules by providing:
- Standardized provider integration patterns
- Common model management infrastructure
- Enhanced messaging backbone for AI conversations
- Security framework for AI operations
- Configuration management for AI services

### 1. LLM.Thread (`llm_thread/models/llm_thread.py`)
**Purpose**: Central bridge between Odoo data and LLM conversations

```python
class LLMThread(models.Model):
    _name = "llm.thread"
    _description = "LLM Chat Thread"
    _inherit = ["mail.thread"]
```

**Core Function**: The `llm.thread` model serves as the primary link between Odoo's business data and AI conversations. It acts as an LLM-enabled `mail.thread` that:

- **Storage Backend**: Serves as the persistent storage for all LLM conversations in Odoo
- **Data Bridge**: Links any Odoo record to one or more AI conversation threads
- **Conversation Context**: Maintains the state, configuration, and history of AI interactions
- **Multi-Threading**: Enables multiple concurrent AI conversations per business record (e.g., multiple chat threads for a single sale order)

**Conceptual Model**: Think of `llm.thread` as `mail.thread` with AI superpowers - it inherits all mail functionality while adding LLM-specific capabilities like provider management, tool execution, and structured AI message handling.

**Key Fields**:
- `name`: Thread title
- `provider_id`: Many2one to `llm.provider` - Which AI service to use
- `model_id`: Many2one to `llm.model` - Specific AI model for this conversation
- `tool_ids`: Many2many to `llm.tool` - Available tools for AI function calling
- `model`: Related document model (for record linking) - Links to any Odoo model
- `res_id`: Related document ID - Specific record instance
- `assistant_id`: Many2one to `llm.assistant` - AI assistant configuration
- `prompt_id`: Many2one to `llm.prompt` - Template for conversation structure

**Key Methods**:
- `message_post()`: Enhanced to handle `llm_role` parameter for AI message types
- `message_post_from_stream()`: Real-time streaming message creation during AI generation
- `_get_llm_email_from()`: Generate appropriate sender addresses for different AI roles
- `set_assistant()`: Configure the AI assistant and its associated tools/prompts

**Relationship Pattern**:
```
Odoo Record (sale.order, project.task, etc.)
    ↓ (1:many relationship)
LLM Thread(s) - Multiple AI conversations per record
    ↓ (inherits from mail.thread)
Mail Messages - Conversation history with AI-specific enhancements
```

### 2. LLM.Assistant (`llm_assistant/models/llm_assistant.py`)
**Purpose**: Intelligent configuration orchestrator for AI interactions

```python
class LLMAssistant(models.Model):
    _name = "llm.assistant"
    _description = "LLM Assistant"
    _inherit = ["mail.thread"]
```

**Core Function**: The `llm.assistant` model serves as the intelligent glue that defines HOW to connect Odoo data to AI models. While `llm.thread` provides the data management backend, `llm.assistant` provides the intelligence layer that configures:

- **Model Selection**: Specifies which AI provider and model to use (chat, generation, media, training, etc.)
- **Instruction Templates**: Defines system prompts, message templates, and generation prompts
- **Data Mapping**: How to transform Odoo record data into LLM-compatible inputs
- **Tool Orchestration**: Which tools are available and how they should be used
- **Context Management**: Intelligence for conversation history trimming and context optimization
- **Generation Configuration**: Templates for different types of content generation (text, images, etc.)

**Conceptual Model**: Think of `llm.assistant` as the "brain" that knows how to operate the "body" (`llm.thread`). The thread manages the data and conversations, while the assistant provides the configuration, instructions, and intelligence for how AI should interact with that data.

**Key Fields**:
- `name`: Assistant identifier
- `role`: Assistant role/persona definition
- `goal`: Assistant's primary objective and purpose
- `background`: Context, expertise, and domain knowledge description
- `instructions`: Detailed operational instructions for AI behavior
- `provider_id`: Default AI provider (OpenAI, Anthropic, etc.)
- `model_id`: Default AI model (GPT-4, Claude, local models, etc.)
- `tool_ids`: Preferred tools available to this assistant
- `prompt_id`: Associated prompt template for structured interactions
- `default_values`: Default argument values for prompt templates
- `context_window_management`: Rules for conversation history trimming

**Key Methods**:
- `get_system_prompt()`: Generate system prompt from role, goal, and instructions
- `prepare_context()`: Transform Odoo data into LLM-compatible context
- `get_available_tools()`: Return configured tools for this assistant
- `trim_conversation_history()`: Intelligent context window management
- `map_generation_inputs()`: Transform Odoo data to generation parameters

**Assistant Types & Use Cases**:

1. **Chat Assistants**: Configure conversational AI with specific personas
   - Customer service bots with access to CRM tools
   - Technical support with knowledge base access
   - Sales assistants with product and pricing tools

2. **Generation Assistants**: Configure content creation workflows
   - Marketing copy generation from product data
   - Report generation from business metrics
   - Image generation from product specifications

3. **Training Assistants**: Configure model fine-tuning workflows
   - Dataset preparation from Odoo records
   - Training parameter optimization
   - Model evaluation and deployment

4. **Analysis Assistants**: Configure data analysis workflows
   - Business intelligence from ERP data
   - Predictive analytics on sales data
   - Quality analysis from manufacturing records

**Data Flow Architecture**:
```
Odoo Record Data
    ↓
LLM Thread (data storage & management)
    ↓
LLM Assistant (intelligent configuration)
    ├── Provider/Model Selection
    ├── Instruction Templates
    ├── Tool Configuration
    ├── Context Mapping
    └── History Management
    ↓
AI Provider API (OpenAI, Anthropic, etc.)
    ↓
Generated Response/Content
    ↓
Back to LLM Thread (storage)
```

**Template Integration**: Assistants can reference `llm.prompt` templates that define:
- System message templates with Odoo data placeholders
- Multi-step conversation flows
- Generation parameter mapping from business records
- Context injection patterns for domain-specific knowledge

### 3. LLM.Provider (`llm/models/llm_provider.py`)
**Purpose**: AI service provider abstraction
```python
class LLMProvider(models.Model):
    _name = "llm.provider"
    _inherit = ["mail.thread"]
    _description = "LLM Provider"
```

**Key Fields**:
- `name`: Provider name
- `service`: Selection field for service type
- `api_key`: API authentication
- `api_base`: Base URL for API calls
- `model_ids`: One2many to `llm.model`

**Key Methods**:
- `_dispatch()`: Dynamic method dispatch to service implementations
- `chat()`: Chat completion interface
- `embedding()`: Text embedding generation
- `generate()`: Generic content generation

### 4. LLM.Model (`llm/models/llm_model.py`)
**Purpose**: AI model configuration
```python
class LLMModel(models.Model):
    _name = "llm.model"
    _description = "LLM Model"
    _inherit = ["mail.thread"]
```

**Key Fields**:
- `name`: Model identifier
- `provider_id`: Parent provider
- `publisher_id`: Model publisher (OpenAI, Anthropic, etc.)
- `model_use`: Selection ('chat', 'embedding', 'multimodal', etc.)
- `default`: Default model for its use type
- `details`: JSON metadata
- `parameters`: Model parameters

### 5. LLM.Tool (`llm_tool/models/llm_tool.py`)
**Purpose**: Function calling capabilities
```python
class LLMTool(models.Model):
    _name = "llm.tool"
    _description = "LLM Tool"
    _inherit = ["mail.thread"]
```

**Key Fields**:
- `name`: Tool identifier
- `description`: Human-readable description
- `implementation`: Selection for tool type
- `input_schema`: JSON schema for parameters
- `requires_user_consent`: Security flag
- Various hint fields (`read_only_hint`, `destructive_hint`, etc.)

**Key Methods**:
- `execute()`: Execute tool with validated parameters
- `get_input_schema()`: Generate schema from method signature
- `get_tool_definition()`: Return MCP-compatible tool definition

### 6. LLM.Prompt (`llm_assistant/models/llm_prompt.py`)
**Purpose**: Template management and rendering
```python
class LLMPrompt(models.Model):
    _name = "llm.prompt"
    _description = "LLM Prompt Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
```

**Key Fields**:
- `name`: Template identifier
- `template`: Jinja2 template content
- `format`: Selection ('text', 'yaml', 'json')
- `arguments_json`: JSON schema for template variables
- `category_id`: Categorization
- `tag_ids`: Many2many tags

**Key Methods**:
- `get_messages()`: Render template with arguments
- `_fill_default_values()`: Apply default argument values
- `_ensure_arguments_sync()`: Auto-detect template arguments

## Thread ↔ Related Record Connection

### Related Record Linking
Threads can be linked to any Odoo record via:
```python
# In LLMThread model
model = fields.Char(string="Related Document Model")
res_id = fields.Many2oneReference(string="Related Document ID", model_field="model")
```

### Frontend Integration
The `llm_chat_thread_related_record` component provides:
- Visual indicator of linked record
- Record picker dialog for linking
- Navigation to related record
- Unlinking functionality

### Usage Pattern
```python
# Create thread linked to a sale order
thread = env['llm.thread'].create({
    'name': 'Sales Discussion',
    'model': 'sale.order',
    'res_id': sale_order.id,
    'provider_id': provider.id,
    'model_id': model.id
})
```

## Prompt Rendering & Formats

### Template Engine
Uses Jinja2 for template rendering:
```python
from ..utils import render_template

rendered = render_template(template=self.template, context=arguments)
```

### Supported Formats

#### 1. Text Format
Simple string templates:
```
Hello {{user_name}}, please analyze: {{data_input}}
```

#### 2. YAML Format
Structured message format:
```yaml
messages:
  - type: system
    content: |
      You are a helpful assistant. User: {{user_name}}
  - type: user
    content: |
      Please analyze: {{data_input}}
```

#### 3. JSON Format
Direct API format:
```json
{
  "messages": [
    {
      "type": "system", 
      "content": "You are {{role}}. User: {{user_name}}"
    },
    {
      "type": "user",
      "content": "{{user_input}}"
    }
  ]
}
```

### Argument Schema
Prompts define expected arguments via JSON Schema:
```json
{
  "user_name": {
    "type": "string",
    "description": "Name of the user",
    "required": true,
    "default": "User"
  },
  "data_input": {
    "type": "string", 
    "description": "Data to analyze",
    "required": true
  }
}
```

## Vector Stores & Knowledge System

### Vector Store Architecture
Base abstraction in `llm_store/models/llm_store.py`:
```python
class LLMStore(models.Model):
    _name = "llm.store"
    _inherit = ["mail.thread"] 
    _description = "LLM Vector Store"
    
    def _dispatch(self, method, *args, **kwargs):
        """Dispatch to service-specific implementation"""
        service_method = f"{self.service}_{method}"
        return getattr(self, service_method)(*args, **kwargs)
```

### Supported Vector Stores
- **Chroma** (`llm_chroma`): HTTP client integration
- **pgvector** (`llm_pgvector`): PostgreSQL extension
- **Qdrant** (`llm_qdrant`): Qdrant vector database

### Knowledge Management
The `llm_knowledge` module provides:
- **Resource Management**: `llm.resource` for documents
- **Chunking**: `llm.knowledge.chunk` for text segments  
- **Collections**: `llm.knowledge.collection` for organization
- **Retrievers**: Semantic search capabilities

### RAG Integration
Tools can retrieve knowledge via `llm_tool_knowledge`:
```python
class LLMToolKnowledgeRetriever(models.Model):
    _name = "llm.tool.knowledge.retriever"
    _inherit = "llm.tool"
    
    def knowledge_retriever_execute(self, query, collection_id=None, limit=5):
        """Retrieve relevant knowledge chunks"""
        # Vector similarity search implementation
```

## MCP (Model Context Protocol) Integration

### MCP Server (`llm_mcp/models/llm_mcp_server.py`)
Exposes Odoo capabilities via MCP:
```python
class LLMMCPServer(models.Model):
    _name = "llm.mcp.server"
    _description = "MCP Server Configuration"
    
    # Server configuration
    name = fields.Char(required=True)
    command = fields.Char(required=True)  # Command to start server
    args = fields.Text()  # Command arguments
    env_vars = fields.Json()  # Environment variables
```

### MCP Bus Manager
Handles MCP server lifecycle:
- Server process management
- Transport coordination (stdio/http)
- Message routing between clients and servers

### Tool Integration
Tools can be exposed via MCP for external LLM access:
```python
def get_tool_definition(self):
    """Returns MCP-compatible tool definition"""
    return {
        "name": self.name,
        "description": self.description,
        "inputSchema": json.loads(self.input_schema or '{}')
    }
```

## Message System & Roles

### Enhanced Mail Message
Extended `mail.message` with LLM-specific fields:
```python
# In mail_message.py extensions
llm_role = fields.Selection([
    ('user', 'User'),
    ('assistant', 'Assistant'), 
    ('tool', 'Tool'),
    ('system', 'System')
])
body_json = fields.Json()  # Structured data for tool messages
```

### Message Creation Pattern
```python
# Clean role-based message posting
thread.message_post(
    body="Hello, how can I help?",
    llm_role="assistant",
    author_id=False  # AI-generated
)

# Tool execution result
thread.message_post(
    body_json={
        "tool_call_id": "call_123",
        "content": {"result": "success", "data": {...}}
    },
    llm_role="tool"
)
```

### Streaming Messages
Real-time message updates:
```python
def message_post_from_stream(self, stream, llm_role, **kwargs):
    """Create and update message from streaming response"""
    # Creates placeholder message, updates content as stream progresses
```

## Generation System Architecture

### Unified Generation API
The `llm_generate` module provides:
```python
# In llm_thread model
def generate_response(self, user_input, use_queue=None):
    """Generate AI response with automatic provider selection"""
    # Handles both immediate and queued generation
```

### Queue Management (`llm_generate_job`)
- **Job Model**: `llm.generation.job` tracks individual generation tasks
- **Queue Model**: `llm.generation.queue` manages provider-specific queues
- **Automatic Queueing**: Based on provider capabilities and load

### Content Generation Flow
1. **Input Processing**: Validate and prepare generation inputs
2. **Model Selection**: Choose appropriate model for task
3. **Generation**: Execute via provider (immediate or queued)
4. **Result Processing**: Parse and store generated content
5. **Message Creation**: Create message with generated content

## Provider Integration Pattern

### Service Registration
Providers register services via:
```python
@api.model
def _get_available_services(self):
    return super()._get_available_services() + [
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic'),
        # etc.
    ]
```

### Method Implementation
Service-specific methods follow naming convention:
```python
def openai_chat(self, messages, model=None, stream=False, **kwargs):
    """OpenAI-specific chat implementation"""
    
def anthropic_chat(self, messages, model=None, stream=False, **kwargs):
    """Anthropic-specific chat implementation"""
```

### Supported Providers
- **OpenAI** (`llm_openai`): GPT models, DALL-E
- **Anthropic** (`llm_anthropic`): Claude models
- **Ollama** (`llm_ollama`): Local model deployment
- **Mistral** (`llm_mistral`): Mistral AI models
- **Replicate** (`llm_replicate`): Model marketplace
- **FAL.ai** (`llm_fal_ai`): Fast inference API
- **LiteLLM** (`llm_litellm`): Multi-provider proxy

## Security & Access Control

### User Groups
- **LLM User** (`llm.group_llm_user`): Basic access
- **LLM Manager** (`llm.group_llm_manager`): Full administration

### Tool Consent System
Tools can require user consent:
```python
requires_user_consent = fields.Boolean(default=False)
```

### Record Rules
- Users can only access their own threads
- System administrators have full access
- Company-based access control for providers

## Frontend Architecture

### JavaScript Models
The frontend uses Odoo's OWL framework with:
- **LLMChat**: Main chat interface controller
- **Thread**: Thread management and message handling  
- **LLMModel**: Model information and capabilities
- **LLMTool**: Tool definitions and execution
- **LLMAssistant**: Assistant configuration

### Key Components
- **LLMChatContainer**: Main chat interface
- **LLMChatComposer**: Message input and media generation
- **LLMChatThreadHeader**: Provider/model/assistant selection
- **LLMChatThreadRelatedRecord**: Related record management
- **LLMMediaForm**: Dynamic form generation for model inputs

### Real-time Features
- **Streaming**: Live message updates during generation
- **Tool Execution**: Visual feedback for tool calls
- **Model Switching**: Dynamic provider/model selection
- **Assistant Switching**: Context-aware assistant changes

## Development Patterns

### Adding New Providers
1. Create module inheriting from `llm.provider`
2. Implement service-specific methods
3. Register service in `_get_available_services()`
4. Add provider-specific configuration

### Creating Custom Tools
1. Inherit from `llm.tool`  
2. Implement `{implementation}_execute()` method
3. Define input schema via method signature or JSON
4. Register implementation in `_get_available_implementations()`

### Extending Message Handling
1. Override `message_post()` in thread model
2. Handle custom `llm_role` values
3. Process `body_json` for structured data
4. Implement custom email_from patterns

This architecture provides a robust, extensible foundation for building sophisticated AI-powered applications within Odoo, with clear separation of concerns and consistent patterns for extension and customization.
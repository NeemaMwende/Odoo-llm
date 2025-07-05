# LLM Assistant with Prompt Templates

This Odoo module provides comprehensive AI assistant capabilities with integrated prompt template management for LLM interactions. It combines assistant configuration with reusable prompt templates to create powerful, specialized AI assistants.

## Features

### Assistant Management

- **Assistant Configuration**: Create and configure AI assistants with specific roles and goals
- **Tool Integration**: Assign preferred tools to each assistant for specialized capabilities
- **System Prompt Generation**: Automatically generate system prompts based on assistant configuration
- **Thread Integration**: Attach assistants to chat threads for consistent behavior
- **UI Integration**: Seamlessly switch between assistants in the chat interface

### Prompt Template Management

- **Reusable Templates**: Create and manage prompt templates that can be reused across LLM interactions
- **Multiple Formats**: Support for Text, YAML, and JSON template formats
- **Dynamic Arguments**: Define arguments within prompts using {{argument_name}} syntax
- **Multi-step Workflows**: Create complex prompt sequences with different roles (system, user, assistant)
- **Categorization**: Organize prompts with categories and tags for easy discovery
- **Enhanced Testing**: Test prompts with context simulation and related record integration
- **Auto-detection**: Automatic argument detection from template content

## Installation

1. Clone the repository into your Odoo addons directory
2. Install the module via the Odoo Apps menu
3. The module will automatically include all prompt template functionality

## Configuration

### Creating Assistants

1. Navigate to LLM > Configuration > Assistants
2. Create new assistants with specific providers and models
3. Configure tools and system prompts for each assistant
4. Assign assistants to specific user groups if needed

### Creating Prompt Templates

1. Navigate to LLM > Prompts
2. Click "Create" to create a new prompt template
3. Configure the template with:
   - **Name**: Unique identifier for the prompt
   - **Description**: Human-readable description
   - **Category**: Select or create a category for organization
   - **Tags**: Add tags for classification
   - **Format**: Choose between Text, YAML, or JSON
   - **Template**: The actual prompt content with {{argument}} placeholders
   - **Arguments Schema**: Define JSON schema for template arguments

### Arguments Schema

The arguments schema defines the structure of arguments used in prompt templates:

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

## Usage

### Creating an Assistant

1. Go to LLM > Configuration > Assistants
2. Click "Create" to add a new assistant
3. Configure the assistant with:
   - Name, provider, and model
   - Prompt template (optional)
   - Preferred tools
   - Default argument values
4. Save the assistant configuration

### Using Prompt Templates

1. Create reusable prompt templates with dynamic arguments
2. Test prompts using the built-in testing wizard
3. Use prompts directly in threads or associate them with assistants
4. Reference prompts in API calls or programmatic usage

### Template Formats

#### Text Format

```
Hello {{user_name}}, please analyze the following data: {{data_input}}
```

#### YAML Format

```yaml
messages:
  - type: system
    content: |
      You are a helpful assistant. The user's name is {{user_name}}.
  - type: user
    content: |
      Please analyze: {{data_input}}
```

#### JSON Format

```json
{
  "messages": [
    {
      "type": "system",
      "content": "You are a helpful assistant. The user's name is {{user_name}}."
    },
    {
      "type": "user",
      "content": "Please analyze: {{data_input}}"
    }
  ]
}
```

### Testing Prompts

1. Open any prompt template
2. Click "Test Prompt" to launch the testing wizard
3. Select a related record to auto-populate context
4. Modify test context as needed
5. View results in JSON, YAML, or text format

### Using Assistants in Chat

1. Open a chat thread from LLM > Threads
2. Select an assistant from the dropdown in the chat header
3. The assistant's configuration (provider, model, tools, prompts) will be applied
4. Start chatting with the configured assistant

## Pre-configured Assistants

The module includes pre-configured assistants:

1. **Assistant Creator**: Guides users through creating and configuring specialized AI assistants in Odoo
2. **Website Builder**: Helps update website content, structure, and functionality within the Odoo system

## API Integration

### Prompt API Endpoints

- `POST /api/llm/prompts/list` - List available prompts
- `POST /api/llm/prompts/get` - Get a specific prompt with arguments
- `POST /llm/thread/set_prompt` - Set prompt for a thread

### Programmatic Usage

```python
# Get a prompt and render it with arguments
prompt = env['llm.prompt'].search([('name', '=', 'my_prompt')])
arguments = {'user_name': 'John', 'data_input': 'sample data'}
messages = prompt.get_messages(arguments)

# Use in a thread
thread = env['llm.thread'].browse(thread_id)
thread.prompt_id = prompt.id
```

## Dependencies

- Odoo 16.0 or later
- Python 3.8 or later
- Required Python packages: jinja2, pyyaml, jsonschema
- Required Odoo modules:
  - base
  - mail
  - web
  - llm
  - llm_thread
  - llm_tool
  - web_json_editor

## Contributing

Contributions are welcome! Please follow the contribution guidelines in the repository.

## License

This module is licensed under the LGPL-3 license.

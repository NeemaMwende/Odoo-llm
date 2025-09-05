# Letta LLM Integration

This module provides integration with Letta platform for Odoo's LLM framework.

## Features

- **Model Fetching**: List available models from Letta (local or cloud)
- **Agent-Based Chat**: Stateful conversations using Letta agents
- **Thread Integration**: Agents created automatically with threads
- **Memory Management**: Uses assistant prompts for agent personas
- **Local/Cloud Support**: Supports both local Letta servers and Letta Cloud
- **Extensible Architecture**: Follows Odoo LLM framework patterns

## Installation

1. Install the required Python package:
   ```bash
   pip install letta-client
   ```

2. Install this module in Odoo

## Configuration

### Local Letta Server

For local development, a default provider "Letta (Local)" is configured to connect to `http://localhost:8283`.

No API key is required for local connections.

### Letta Cloud

1. Create a new provider or modify the "Letta (Cloud)" provider
2. Set your Letta API token in the "API Key" field
3. Set your project name in the "API Base" field (defaults to "default-project")

## Current Limitations

This implementation supports **model fetching and chat functionality**. The following features are not yet implemented:

- Text embeddings (`letta_embedding`) 
- Content generation (`letta_generate`)
- Custom tool integration (basic Letta tools only)

All unimplemented methods will raise `NotImplementedError` with descriptive messages.

## Usage

1. Go to LLM → Providers
2. Find or create a Letta provider
3. Configure API settings
4. Use the "Fetch Models" wizard to retrieve available models
5. Create a thread with Letta provider and model
6. Agent will be created automatically and stored in `thread.external_id`
7. Start chatting - agent maintains conversation history

## Architecture

This module follows the standard Odoo LLM provider pattern:

- Extends `llm.provider` model with Letta-specific methods
- Registers "letta" service in available services
- Uses dispatch pattern for provider-specific method calls
- Provides proper error handling and logging

## Development

To extend this module with additional functionality:

1. Implement the placeholder methods in `models/letta_provider.py`
2. Add message formatting by extending `mail.message` model
3. Add any Letta-specific data models if needed
4. Update tests and documentation
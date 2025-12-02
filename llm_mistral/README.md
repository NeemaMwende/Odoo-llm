# LLM Mistral Integration

Mistral AI provider integration for Odoo LLM modules.

**Module Type:** 🔧 Provider

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Used By (Any LLM Module)                     │
│  ┌─────────────┐  ┌───────────┐  ┌─────────────┐  ┌───────────┐ │
│  │llm_assistant│  │llm_thread │  │llm_knowledge│  │llm_generate│ │
│  └──────┬──────┘  └─────┬─────┘  └──────┬──────┘  └─────┬─────┘ │
└─────────┼───────────────┼───────────────┼───────────────┼───────┘
          │               │               │               │
          └───────────────┴───────┬───────┴───────────────┘
                                  ▼
          ┌───────────────────────────────────────────────┐
          │          ★ llm_mistral (This Module) ★        │
          │              Mistral AI Provider              │
          │  Mistral Large │ Medium │ Small │ Embeddings  │
          └─────────────────────┬─────────────────────────┘
                                │
                                ▼
          ┌───────────────────────────────────────────────┐
          │                    llm                        │
          │              (Core Base Module)               │
          └───────────────────────────────────────────────┘
```

## Installation

### What to Install

**For AI chat with Mistral:**
```bash
odoo-bin -d your_db -i llm_assistant,llm_mistral
```

### Auto-Installed Dependencies
- `llm` (core infrastructure)

### Why Choose Mistral?

| Feature | Mistral |
|---------|---------|
| **Location** | 🇪🇺 European (GDPR friendly) |
| **Speed** | ⚡ Very fast inference |
| **Cost** | 💰 Competitive pricing |
| **Embeddings** | ✅ High-quality embeddings |

### Common Setups

| I want to... | Install |
|--------------|---------|
| Chat with Mistral | `llm_assistant` + `llm_mistral` |
| Mistral + RAG | Above + `llm_knowledge` + `llm_pgvector` |
| Mistral OCR | `llm_knowledge_mistral` (image text extraction) |

## Features

- Chat completion support
- Streaming responses
- Model management
- API key configuration

## Installation

1. Install the module
2. Go to Settings → LLM → Providers
3. Create a Mistral provider with your API key
4. Fetch available models

## Configuration

Set your Mistral API key in the provider configuration.

## Requirements

- Odoo 18.0+
- llm module

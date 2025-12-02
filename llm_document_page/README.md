# LLM Document Page Integration

Integrate LLM capabilities with Odoo Document Pages for intelligent document assistance.

**Module Type:** 🔌 Extension (Document Pages)

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                      Application Layer                        │
│                    ┌───────────────┐                          │
│                    │Document Pages │                          │
│                    │     (OCA)     │                          │
│                    └───────┬───────┘                          │
└────────────────────────────┼──────────────────────────────────┘
                             │
                             ▼
              ┌───────────────────────────────────────────┐
              │  ★ llm_document_page (This Module) ★      │
              │     Document Page + LLM Integration       │
              │  📄 Smart Content │ AI Suggestions        │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
              ┌───────────────────────────────────────────┐
              │                   llm                     │
              │            (Core Base Module)             │
              └───────────────────────────────────────────┘
```

## Installation

### What to Install

**For AI-assisted document pages:**
```bash
odoo-bin -d your_db -i llm_document_page
```

### Auto-Installed Dependencies
- `llm` (core infrastructure)
- `knowledge_document_page` (OCA document pages)

### Why Use This Module?

| Feature | llm_document_page |
|---------|-------------------|
| **Suggestions** | 🤖 AI-powered content suggestions |
| **Integration** | 📄 Native document page integration |
| **Generation** | ✍️ Smart content generation |

### Common Setups

| I want to... | Install |
|--------------|---------|
| AI document pages | `llm_document_page` + `llm_openai` |
| Chat + doc pages | `llm_assistant` + `llm_openai` + `llm_document_page` |

## Features

- AI-powered document suggestions
- Document page integration
- Smart content generation
- Intelligent editing assistance

## Usage

Access LLM features directly from document pages for intelligent content assistance.

## Requirements

- Odoo 18.0+
- `llm` module
- `knowledge_document_page` module (OCA)

## License

LGPL-3

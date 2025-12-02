# LLM ComfyUI Integration

This module integrates Odoo with the ComfyUI API for AI image generation. It provides a new provider type that can be used with the LLM framework.

**Module Type:** 🔧 Provider (Self-Hosted Image Generation)

## Architecture

```
┌───────────────────────────────────────────────────────┐
│             Used By (Generation Modules)              │
│     ┌─────────────┐           ┌───────────┐          │
│     │llm_assistant│           │llm_generate│          │
│     └──────┬──────┘           └─────┬─────┘          │
└────────────┼────────────────────────┼────────────────┘
             └────────────┬───────────┘
                          ▼
          ┌───────────────────────────────────────────┐
          │        ★ llm_comfyui (This Module) ★      │
          │           ComfyUI Provider                │
          │  🖥️ Self-hosted │ Custom Workflows │ GPU  │
          └─────────────────────┬─────────────────────┘
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│           llm             │   │     ComfyUI Server        │
│    (Core Base Module)     │   │   (localhost:8188)        │
└───────────────────────────┘   │   🖥️ Your GPU hardware    │
                                └───────────────────────────┘
```

## Installation

### What to Install

**For self-hosted image generation:**
```bash
# 1. Install ComfyUI on your server with GPU
# See: https://github.com/comfyanonymous/ComfyUI

# 2. Install the Odoo module
odoo-bin -d your_db -i llm_comfyui
```

### Auto-Installed Dependencies
- `llm` (core infrastructure)

### Why Choose ComfyUI?

| Feature | ComfyUI |
|---------|---------|
| **Control** | 🎛️ Custom workflows |
| **Cost** | 💰 Your hardware (no API fees) |
| **Privacy** | 🔒 Data stays local |
| **Flexibility** | ✅ Any model/workflow |

### Common Setups

| I want to... | Install |
|--------------|---------|
| Self-hosted images | `llm_comfyui` (+ ComfyUI server) |
| Chat + local images | `llm_assistant` + `llm_openai` + `llm_comfyui` |

## Features

- Connect to any ComfyUI instance via its HTTP API
- Submit ComfyUI workflows for execution
- Retrieve generated images
- Integrate with the LLM framework for media generation

## Configuration

1. Go to LLM > Configuration > Providers
2. Create a new provider with service type "ComfyUI"
3. Set the API Base URL to your ComfyUI instance (e.g., `http://localhost:8188`)
4. Optionally set an API key if your ComfyUI instance requires authentication
5. Create a model that uses this provider

## Usage

The module expects ComfyUI workflow JSON in the API format. You can obtain this by using the "Save (API Format)" button in the ComfyUI interface (requires "Dev mode options" to be enabled in settings).

## Security

This module follows the standard two-tier security model:

- Regular users (base.group_user) have read-only access
- LLM Managers (llm.group_llm_manager) have full CRUD access

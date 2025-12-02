# LLM Chroma Integration

Chroma vector store integration for development and lightweight production use.

**Module Type:** 🗄️ Vector Store (Development Friendly)

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    Used By (RAG Modules)                      │
│        ┌───────────────┐           ┌───────────────┐         │
│        │ llm_knowledge │           │llm_assistant  │         │
│        │   (RAG)       │           │  (with RAG)   │         │
│        └───────┬───────┘           └───────┬───────┘         │
└────────────────┼───────────────────────────┼─────────────────┘
                 └─────────────┬─────────────┘
                               ▼
              ┌───────────────────────────────────────────┐
              │             llm_store                     │
              │        (Vector Store API)                 │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
              ┌───────────────────────────────────────────┐
              │       ★ llm_chroma (This Module) ★        │
              │          Chroma Implementation            │
              │  🌈 Easy Setup │ HTTP API │ Development   │
              └─────────────────────┬─────────────────────┘
                                    │
                                    ▼
              ┌───────────────────────────────────────────┐
              │              Chroma Server                │
              │           (localhost:8000)                │
              └───────────────────────────────────────────┘
```

## Installation

### What to Install

**For development RAG:**
```bash
# 1. Start Chroma server
docker run -p 8000:8000 chromadb/chroma:1.0.0

# 2. Install Python dependencies
pip install chromadb-client numpy

# 3. Install the Odoo module
odoo-bin -d your_db -i llm_knowledge,llm_chroma
```

### Auto-Installed Dependencies
- `llm` (core infrastructure)
- `llm_store` (vector store abstraction)

### Why Choose Chroma?

| Feature | Chroma |
|---------|--------|
| **Setup** | 🚀 Very easy |
| **Development** | 🛠️ Great for prototyping |
| **API** | 📡 Simple HTTP API |
| **Cost** | 💰 Free & open source |

### Vector Store Comparison

| Feature | llm_pgvector | llm_qdrant | llm_chroma |
|---------|--------------|------------|------------|
| **Server** | 🐘 PostgreSQL | 🔷 Qdrant server | 🌈 Chroma server |
| **Setup** | Easy | Moderate | Easy |
| **Scale** | Medium | High | Medium |
| **Best For** | Simple RAG | Large scale | Development |

### Common Setups

| I want to... | Install |
|--------------|---------|
| Development RAG | `llm_knowledge` + `llm_chroma` |
| Chat + RAG (dev) | `llm_assistant` + `llm_openai` + `llm_knowledge` + `llm_chroma` |

## Features

- **Chroma HTTP Client**: Connect to a Chroma server with optional SSL and API key support
- **Collection Management**: Create, list, delete, and verify collections in Chroma directly from Odoo
- **Vector Operations**: Insert, delete, and search vectors with metadata, IDs, and customizable distance-to-similarity conversion
- **Filter Conversion**: Translate basic Odoo filter formats into Chroma `where` conditions

## Configuration

1. In **LLM > Configuration > Vector Stores**, create or edit a store:
   - **Service**: `chroma`
   - **Connection URI**: e.g., `http://localhost:8000`
   - **API Key** (optional)
2. Ensure your Chroma Docker image matches the client version:
   ```yaml
   image: chromadb/chroma:1.0.0
   ```

## Usage

Once configured, use the `llm.store` methods:

```python
# Create a new collection
store.chroma_create_collection(collection_id)

# Insert embeddings
store.chroma_insert_vectors(collection_id, vectors, metadata=list_of_dicts, ids=list_of_ids)

# Query by embedding or text
results = store.chroma_search_vectors(collection_id, query_vector, limit=10)
```

## Troubleshooting

### KeyError: '\_type'

**Symptom:** A `KeyError: '_type'` when calling `client.create_collection(...)`.

**Cause:** Chroma server expects a `_type` discriminator in the JSON `configuration` payload but didn't receive one, often due to a client/server version mismatch.

**Solutions:**

1. **Pin matching versions**
   ```bash
   pip install chromadb-client==1.0.0
   docker pull chromadb/chroma:1.0.0
   ```
2. **Explicitly supply configuration**
   ```python
   client.create_collection(
       name=collection_name,
       metadata=metadata,
       configuration={
           "_type": "hnsw",
           "hnsw:space": "cosine",
       }
   )
   ```

## Requirements

- Odoo 18.0
- Python packages: `chromadb-client`, `numpy`
- Chroma server instance

## License

LGPL-3

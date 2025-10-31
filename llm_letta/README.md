# Letta LLM Integration

Integrate Letta agents with Odoo - stateful AI conversations with persistent memory and tool access.

## Quick Start

**5 minutes to your first Letta agent:**

```bash
# 1. Install Letta client (forked version required due to bug in original one)
pip install git+https://github.com/apexive/letta-python.git@main

# 2. Start Letta server (Docker)
docker compose up letta -d

# 3. Install module in Odoo
odoo-bin -d your_db -i llm_letta,llm_mcp_server
```

**Usage:**

1. Go to **LLM → Threads** → Create new thread
2. Select **Provider**: "Letta (Local)", **Model**: any available model
3. Start chatting - agent is auto-created with full tool access

**That's it!** Agent remembers context and can use all your active Odoo tools.

## Features

- **Stateful Agents**: Persistent memory across conversations
- **MCP Tool Access**: Uses Odoo tools via Model Context Protocol
- **Auto-sync**: Tools automatically available to agents
- **Streaming**: Real-time responses with tool call logging
- **Local/Cloud**: Supports both Letta server and Letta Cloud

## Requirements

- **Letta server**: Version 0.11.7+ (earlier versions have MCP bugs)
- **Letta client**: Forked version required ([streaming fix](https://github.com/letta-ai/letta-python/issues/25))
- **llm_mcp_server**: Required for tool access

## Docker Setup

**1. Add to docker-compose.yml:**

```yaml
services:
  letta:
    image: letta/letta:latest
    ports:
      - "8083:8083" # Web UI
      - "8283:8283" # API server
    env_file:
      - .env.letta
```

**2. Create Letta database:**

```bash
# Replace POSTGRES_USER with your PostgreSQL username
psql -U POSTGRES_USER postgres -c "CREATE DATABASE letta OWNER POSTGRES_USER"
psql -U POSTGRES_USER letta -c "CREATE EXTENSION vector"

# Example (if your postgres user is 'odoo'):
# psql -U odoo postgres -c "CREATE DATABASE letta OWNER odoo"
# psql -U odoo letta -c "CREATE EXTENSION vector"
```

**3. Configure MCP Server in Odoo:**

- Go to: LLM → Configuration → MCP Server
- Set External URL: `http://host.docker.internal:8069`
- (Allows Letta in Docker to access Odoo running on host)

**4. Create .env.letta:**

```bash
cat > .env.letta <<EOF
LETTA_PG_URI=postgresql://POSTGRES_USER:POSTGRES_PASSWORD@host.docker.internal:5432/letta
OPENAI_API_KEY=your_openai_api_key
OLLAMA_BASE_URL=http://host.docker.internal:11434  # Optional: for local models
EOF

# Example (if postgres user is 'odoo' with password 'odoo'):
# LETTA_PG_URI=postgresql://odoo:odoo@host.docker.internal:5432/letta
```

**5. Start server:**

```bash
docker compose up letta -d
```

Server runs at `http://localhost:8283` (API).

**Manage via web UI:** https://app.letta.com/settings/organization/projects?view-mode=selfHosted

See [Letta docs](https://docs.letta.com/guides/selfhosting) for more.

## Configuration

**Local**: Default "Letta (Local)" provider connects to `localhost:8283` (no API key needed)

**Cloud**:

1. Get API token from [Letta Cloud](https://app.letta.com)
2. In Odoo: LLM → Providers → "Letta (Cloud)"
3. Set API Key and project name (default: "default-project")
4. Use "Fetch Models" wizard to sync available models

## Tool Integration

**Zero-config MCP setup:**

- Letta agents auto-connect to Odoo's MCP server
- API keys generated automatically per user (no manual setup!)
- All active `llm.tool` records instantly available

**Available operations:**

- Record CRUD operations
- Model method execution
- Model inspection

Tools sync automatically when thread tools change. See `TECHNICAL_GUIDE.md` for details.

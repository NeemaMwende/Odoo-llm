# LLM MCP Server for Odoo

This module implements a Model Context Protocol (MCP) server that exposes Odoo's LLM tools to external systems.

## Features

- **HTTP-based MCP Server**: Implements MCP protocol over HTTP transport
- **JSON-RPC 2.0**: Full JSON-RPC 2.0 compliance
- **Automatic Tool Discovery**: All active `llm.tool` records are automatically exposed
- **Tool Execution**: Execute any configured LLM tool via MCP protocol
- **No Authentication** (for now): Currently using `sudo()` for simplicity

## Endpoints

### Main MCP Endpoint
- **URL**: `/mcp`
- **Method**: POST
- **Content-Type**: application/json

### Health Check
- **URL**: `/mcp/health`
- **Method**: GET or POST
- **Returns**: Server status and tools count

## MCP Protocol Methods

### 1. Initialize
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "MCP Client",
      "version": "1.0.0"
    }
  }
}
```

### 2. List Tools
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

### 3. Call Tool
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": {
      "param1": "value1"
    }
  }
}
```

## Testing with cURL

### Initialize
```bash
curl -X POST http://localhost:8069/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "clientInfo": {"name": "test", "version": "1.0"}
    }
  }'
```

### List Tools
```bash
curl -X POST http://localhost:8069/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

### Call a Tool
```bash
curl -X POST http://localhost:8069/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "record_retriever",
      "arguments": {
        "model_name": "res.partner",
        "domain": [["is_company", "=", true]],
        "fields": ["name", "email"],
        "limit": 5
      }
    }
  }'
```

## Integration with External MCP Clients

### Claude Desktop Configuration
Add to Claude Desktop's configuration:
```json
{
  "mcpServers": {
    "odoo": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "http://your-odoo-server:8069/mcp"
      ]
    }
  }
}
```

### With MCP Client Libraries
Most MCP client libraries support HTTP transport. Configure them to point to:
- **URL**: `http://your-odoo-server:8069/mcp`
- **Transport**: `streamable_http`
- **Protocol**: JSON-RPC 2.0

## Next Steps (Future Enhancements)

1. **Authentication**: Add session-based authentication
2. **User Context**: Track which user is making tool calls
3. **Permissions**: Respect Odoo security rules
4. **Tool Filtering**: Allow filtering tools by category or capability
5. **Streaming**: Support streaming responses for long-running operations

## Development

To add more capabilities, extend the `MCPServerController` class in `controllers/mcp_controller.py`.

The controller follows the MCP specification from: https://github.com/anthropics/mcp
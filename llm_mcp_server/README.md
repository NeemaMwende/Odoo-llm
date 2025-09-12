# LLM MCP Server for Odoo

This module implements a Model Context Protocol (MCP) server that exposes Odoo's LLM tools to external systems.

## Features

- **MCP Protocol Compliance**: Full Model Context Protocol implementation with streamable_http transport
- **JSON-RPC 2.0**: Complete JSON-RPC 2.0 specification compliance  
- **Multiple Response Modes**: Support for both JSON and Server-Sent Events (SSE) responses
- **Session Management**: Stateful and stateless operation modes
- **Resumability**: Stream resumption with event replay for connection recovery
- **Authentication**: API key-based authentication with Bearer tokens
- **Automatic Tool Discovery**: All active `llm.tool` records are automatically exposed as MCP tools
- **Tool Execution**: Execute any configured LLM tool via MCP protocol
- **Comprehensive Testing**: Full test suite with curl-based integration tests

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

## Integration with Claude Desktop

### Prerequisites

1. **Install mcp-remote globally**:
   ```bash
   npm install -g mcp-remote
   ```

2. **Get your API key** from Odoo:
   - Go to: **LLM → Configuration → MCP Server**
   - Copy the **API Key** value

### Claude Desktop Configuration

Add this configuration to your Claude Desktop config file:

**Location**: `~/.config/claude_desktop/claude_desktop_config.json` (Linux/macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "odoo-llm-mcp-server": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://localhost:8069/mcp",
        "--header",
        "Authorization: Bearer YOUR_API_KEY_HERE"
      ],
      "env": {
        "MCP_TRANSPORT": "streamable-http"
      }
    }
  }
}
```

**⚠️ Important**: Replace `YOUR_API_KEY_HERE` with your actual API key from the Odoo MCP Server configuration.

### Server Configuration Modes

The MCP server supports different operational modes via configuration:

- **Stateless Mode**: True/False (session management)
- **JSON Response Mode**: True/False (JSON vs SSE responses)  
- **Enable Resumability**: True/False (stream resumption support)

Configure these in: **LLM → Configuration → MCP Server**

### Testing the Connection

After adding the configuration to Claude Desktop:

1. **Restart Claude Desktop**
2. **Start a new conversation**
3. **Type**: "What tools do you have available?"
4. **Expected**: Claude should list your Odoo LLM tools

### Other MCP Client Libraries

For other MCP clients, configure them to connect to:

- **URL**: `http://your-odoo-server:8069/mcp`
- **Transport**: `streamable_http` 
- **Protocol**: JSON-RPC 2.0
- **Authentication**: Bearer token with API key

## Testing

The module includes a comprehensive test suite located in `curl_test_scripts/`:

```bash
cd curl_test_scripts/

# Quick smoke test
./run_all_tests.sh quick

# Test current server configuration  
./run_all_tests.sh current

# Mode-specific tests
./run_all_tests.sh mode1  # Stateless + JSON
./run_all_tests.sh mode3  # Stateful + JSON  
./run_all_tests.sh mode4  # Stateful + SSE

# Test resumability features
./run_all_tests.sh resumability
```

See `curl_test_scripts/README.md` for detailed testing documentation.

## Security & Access Control

### ✅ **Current Implementation**
- **User Context Tracking**: All tool calls track the authenticated user
- **API Key Authentication**: Integrated with Odoo's `res.users.apikeys` system  
- **Permission Enforcement**: Respects Odoo's built-in access control (ACL) rules
- **Tool-Level Security**: Each tool execution checks user read permissions
- **Audit Logging**: User access attempts and tool executions are logged

### **Access Control Flow**
1. **API Key Validation**: Uses `res.users.apikeys._check_credentials()`
2. **User Binding**: Request environment bound to API key owner via `request.update_env(user=uid)`
3. **Permission Check**: `tool.check_access('read')` validates user access to specific tools
4. **Execution Context**: Tool executes in authenticated user's context (no sudo)

## Next Steps (Future Enhancements)

1. **Tool Filtering**: Allow filtering tools by category or capability in tools/list
2. **Rate Limiting**: Per-user request throttling
3. **Enhanced Logging**: Structured audit logs with detailed tool execution metrics
4. **Permission Caching**: Cache permission checks for improved performance  
5. **WebSocket Support**: Direct WebSocket transport (alternative to mcp-remote)

## Development

To add more capabilities, extend the `MCPServerController` class in `controllers/mcp_controller.py`.

The controller follows the MCP specification from: https://github.com/anthropics/mcp

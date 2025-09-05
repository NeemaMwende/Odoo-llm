# Odoo MCP Server - Technical Guide

## Overview

The `llm_mcp_server` module implements a Model Context Protocol (MCP) server that exposes Odoo's LLM tools to external systems like Letta, Claude Desktop, and other MCP-compatible clients. This allows AI agents running outside of Odoo to discover and execute Odoo tools via the standardized MCP protocol.

## Architecture

### Core Components

- **MCP Server Controller** (`controllers/mcp_controller.py`): HTTP-based JSON-RPC 2.0 server implementing the MCP protocol
- **Tool Discovery**: Automatic exposure of all active `llm.tool` records as MCP tools
- **Schema Patching**: OpenAI compatibility layer for tool parameters
- **Session Management**: Placeholder for future user context tracking

### Protocol Implementation

The server implements MCP protocol over HTTP transport using pure JSON-RPC 2.0:

- **Endpoint**: `/mcp`
- **Transport**: `streamable_http`
- **Protocol**: JSON-RPC 2.0
- **Authentication**: None (currently uses `sudo()` for simplicity)

## Setup and Installation

### 1. Install the Module

```bash
# In your Odoo instance
./odoo-bin -d your_database -u llm_mcp_server
```

### 2. Verify Installation

Check that the MCP server is accessible:

```bash
# Health check
curl http://localhost:8069/mcp/health

# MCP initialize test
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

### 3. Configure External MCP Clients

For **Letta** (or similar systems):

```python
# Register MCP server with Letta
letta_client.tools.add_mcp_server(
    server_name="odoo_mcp",
    server_url="http://your-odoo-server:8069/mcp",
    type="streamable_http"
)
```

For **Claude Desktop**:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "mcp-client",
      "args": ["--url", "http://your-odoo-server:8069/mcp"]
    }
  }
}
```

## Troubleshooting Journey

### Issue 1: JSON-RPC Protocol Mismatches

**Problem**: MCP clients were receiving malformed JSON-RPC responses that failed validation.

**Root Cause**: Using Odoo's `type='json'` endpoint caused double-wrapping of responses and incorrect ID handling:

```json
// Broken response from type='json'
{
  "jsonrpc": "2.0",
  "id": null,  // ← Invalid ID broke client validation
  "result": {...}
}
```

**Solution**: Switched to `type='http'` with manual JSON-RPC 2.0 implementation:

```python
@http.route('/mcp', type='http', auth='none', methods=['POST'], csrf=False)
def mcp_server(self):
    raw_body = request.httprequest.get_data(as_text=True)
    params = json.loads(raw_body)

    response = {
        "jsonrpc": "2.0",
        "id": self._ensure_valid_id(params.get('id')),  # ← Proper ID handling
        "result": {...}
    }
```

**Key Insight**: Odoo's JSON-RPC format is incompatible with standard JSON-RPC 2.0 that MCP requires.

### Issue 2: OpenAI Tool Schema Validation Failures

**Problem**: Letta forwarded tools to OpenAI, which rejected them with:

```
Invalid schema for function 'odoo_model_inspector': array schema missing items
```

**Root Cause**: Pydantic's `model_json_schema()` generated incomplete schemas for modern Python type hints:

```python
# Modern Python syntax
method_type_filter: Optional[list[str]] = None

# Generated broken schema
{
  "type": "array"  // Missing "items": {"type": "string"}
}
```

**Solution**: Implemented schema patching (same approach as `llm_openai` module):

```python
def _patch_schema_for_openai_compatibility(self, schema_node):
    """Fix array schemas that don't specify items type"""
    if "items" in schema_node and isinstance(schema_node["items"], dict):
        items_dict = schema_node["items"]
        if "type" not in items_dict:
            items_dict["type"] = "string"  # Default for OpenAI compatibility
```

**Key Insight**: Modern Python type hints (`list[str]`) don't translate perfectly to OpenAI-compatible JSON Schema via Pydantic. The same patching logic exists in Odoo's OpenAI provider for the same reason.

### Issue 3: Request ID Validation Failures

**Problem**: MCP client validation errors for `id: null` in responses.

**Root Cause**: JSON-RPC 2.0 requires response IDs to be strings or integers, never null.

**Solution**: Added timestamp-based ID generation for missing request IDs:

```python
def _ensure_valid_id(self, request_id):
    if request_id is not None:
        return request_id
    return int(time.time() * 1000)  # Milliseconds since epoch
```

### Issue 4: Code Duplication in Response Building

**Problem**: Repetitive JSON-RPC response construction across all handler methods.

**Solution**: Refactored to DRY principles with helper methods:

```python
def _json_rpc_http_response(self, request_id, result=None, error=None):
    """Build and return a JSON-RPC HTTP response"""
    response = self._build_json_rpc_response(request_id, result, error)
    return http.Response(json.dumps(response), headers={'Content-Type': 'application/json'})
```

## Tested Tools

### ✅ Working Tools (Verified)

These tools have been tested and work correctly with external MCP clients:

1. **`odoo_record_retriever`**: Searches and retrieves Odoo records
2. **`odoo_record_updater`**: Updates existing Odoo records
3. **`odoo_record_unlinker`**: Deletes Odoo records

### ⚠️ Untested Tools

All other tools in your Odoo instance are automatically exposed via MCP but have **not been tested** with external clients. They may produce unexpected results or fail due to:

- Complex parameter types that don't translate well to JSON Schema
- Missing error handling for edge cases
- Assumptions about execution context that don't apply to external clients

**Recommendation**: Test additional tools individually before relying on them in production workflows.

## Current Limitations

### 1. **No Authentication**

- Uses `sudo()` for all operations
- No user context tracking
- No permission enforcement

### 2. **No Session Management**

- Stateless tool execution
- No audit trail of external usage
- Can't track which external user performed actions

### 3. **Limited Error Handling**

- Basic error responses
- No detailed error codes
- Tool execution failures return generic messages

### 4. **Performance Concerns**

- No rate limiting
- No caching of tool definitions
- Each request searches database for tools

## Improvements Needed

### High Priority

1. **Authentication & Authorization**

   ```python
   # Add session-based auth
   def _authenticate_mcp_request(self, headers):
       session_token = headers.get('X-Odoo-Session-Token')
       return self._validate_session(session_token)
   ```

2. **User Context Tracking**

   ```python
   # Log tool usage with user context
   env['mcp.tool.usage'].create({
       'tool_id': tool.id,
       'external_user': session_data.user,
       'arguments': json.dumps(arguments),
       'timestamp': fields.Datetime.now()
   })
   ```

3. **Better Error Handling**
   ```python
   # Structured error responses
   TOOL_ERROR_CODES = {
       'TOOL_NOT_FOUND': -32001,
       'INVALID_ARGUMENTS': -32002,
       'PERMISSION_DENIED': -32003,
       'EXECUTION_FAILED': -32004
   }
   ```

### Medium Priority

4. **Performance Optimization**

   - Cache tool definitions
   - Add rate limiting per client
   - Implement connection pooling

5. **Enhanced Tool Support**

   - Test and fix remaining tools
   - Add streaming support for long-running operations
   - Better parameter validation

6. **Monitoring & Debugging**
   - Detailed request/response logging
   - Performance metrics
   - Health monitoring dashboard

### Low Priority

7. **Protocol Enhancements**
   - Support additional MCP transports (WebSocket, stdio)
   - Resource and prompt support beyond tools
   - Custom MCP extensions

## Security Considerations

⚠️ **WARNING**: Current implementation has significant security risks:

- **No authentication**: Any client can execute any tool
- **Full system access**: Uses `sudo()` with no restrictions
- **No audit trail**: External usage is not tracked
- **No rate limiting**: Vulnerable to abuse

**Do not deploy to production** without implementing proper authentication and authorization.

## Development Notes

### Adding New MCP Methods

To add support for additional MCP protocol methods:

```python
# In mcp_server() method
elif method == 'your_new_method':
    return self._http_handle_your_method(request_id, request_params)

# Add handler method
def _http_handle_your_method(self, request_id, params):
    try:
        # Your logic here
        result = {"your": "data"}
        return self._json_rpc_http_response(request_id, result=result)
    except Exception as e:
        return self._http_error_response(request_id, -32603, str(e))
```

### Schema Patching for New Tool Types

If you encounter schema validation issues with new tools:

```python
# Extend _patch_schema_for_openai_compatibility()
def _patch_schema_for_openai_compatibility(self, schema_node):
    # Existing array patching...

    # Add new schema fixes as needed
    if "your_problematic_type" in schema_node:
        # Fix the schema issue
        pass
```

## Integration Examples

### Letta Agent Integration

```python
# Letta agent can now call Odoo tools
result = await agent.call_tool("odoo_record_retriever", {
    "model": "res.partner",
    "domain": [["is_company", "=", True]],
    "fields": ["name", "email"],
    "limit": 10
})
```

### Claude Desktop Integration

After MCP server configuration, Claude Desktop users can:

- "Show me the top 10 customers in Odoo"
- "Update the contact information for customer X"
- "Delete the obsolete product records"

## Conclusion

The Odoo MCP Server successfully bridges Odoo's LLM tools with external AI agents using the standardized MCP protocol. While the current implementation works for basic use cases, significant security and functionality improvements are needed for production deployment.

The troubleshooting journey revealed important insights about JSON-RPC protocol compatibility and modern Python type hint handling that will benefit future development of similar integrations.

## References

- [Model Context Protocol Specification](https://github.com/anthropics/mcp)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [Odoo LLM Tools Documentation](../llm_tool/README.md)
- [OpenAI Tools API Documentation](https://platform.openai.com/docs/guides/function-calling)

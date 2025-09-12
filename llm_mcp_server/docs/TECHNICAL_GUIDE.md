# Odoo MCP Server - Technical Guide

## Overview

The `llm_mcp_server` module implements a Model Context Protocol (MCP) server that exposes Odoo's LLM tools to external systems like Letta, Claude Desktop, and other MCP-compatible clients. This allows AI agents running outside of Odoo to discover and execute Odoo tools via the standardized MCP protocol.

## Architecture

### Core Components

The server follows a clean component-based architecture:

- **MCP Server Controller** (`controllers/mcp_controller.py`): Thin orchestration layer that coordinates components
- **MCP Transport** (`mcp_transport.py`): HTTP/SSE transport with streaming and resumability support
- **MCP Validator** (`mcp_validator.py`): Protocol validation and API key authentication
- **MCP Request Handler** (`mcp_request_handler.py`): JSON-RPC method routing and tool execution
- **MCP Session Manager** (`mcp_session_manager.py`): Session lifecycle and configuration management
- **Event Store** (`event_store.py`): Event storage for SSE resumability and replay
- **MCP Exceptions** (`mcp_exceptions.py`): Custom exception hierarchy for proper error handling

### Protocol Implementation

The server implements MCP protocol with multiple operational modes:

- **Endpoint**: `/mcp`
- **Transport**: `streamable_http` with SSE infrastructure
- **Protocol**: JSON-RPC 2.0 with MCP SDK compliance
- **Authentication**: API key-based with Bearer token support
- **Tool Execution**: Synchronous execution with immediate responses
- **Session Management**: Stateful and stateless modes
- **SSE Support**: Infrastructure ready for future streaming use cases
- **Configuration**: 4 operational modes via database configuration

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

### 3. Configure Server Settings

Configure the MCP server in Odoo UI:

- **Path**: LLM → Configuration → MCP Server
- **Settings**:
  - **API Key**: Generate/copy for client authentication
  - **Stateless Mode**: True/False (session management)
  - **JSON Response Mode**: True/False (JSON vs SSE responses)
  - **Enable Resumability**: True/False (stream resumption support)

### 4. Configure External MCP Clients

**Prerequisites**: Install mcp-remote globally:

```bash
npm install -g mcp-remote
```

For **Claude Desktop**, add to config file:

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

**Note**: Replace `YOUR_API_KEY_HERE` with your actual API key from Odoo.

## Current Tool Execution Model

### Synchronous Tool Execution

The current implementation uses **synchronous tool execution** for optimal performance with typical Odoo operations:

```python
# Current execution flow
POST /mcp → tools/call → tool.execute(arguments) → immediate result → JSON response
```

**Typical execution times:**

- `odoo_record_retriever`: < 1 second (database queries)
- `odoo_record_updater`: < 1 second (record updates)
- `odoo_record_unlinker`: < 1 second (record deletion)

### SSE Infrastructure Status

While the server includes complete SSE (Server-Sent Events) infrastructure with resumability, it's currently used for:

✅ **Active Use Cases:**

- **Protocol compliance** - Full MCP streamable_http transport support
- **Session management** - Stateful connection handling
- **Testing infrastructure** - Comprehensive test coverage

🔄 **Future Use Cases (Infrastructure Ready):**

- **Long-running operations** - Bulk record processing with progress updates
- **Background job integration** - Async operations with status streaming
- **Real-time notifications** - Server-initiated events for config changes

### When SSE Streaming Will Be Valuable

SSE streaming will become important for:

- **Bulk operations**: Processing 1000+ records with progress reporting
- **Complex reports**: Multi-step report generation with status updates
- **External integrations**: API calls with real-time progress
- **Multi-step workflows**: Operations requiring user confirmations

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

### Issue 2: Tool Schema Generation

**Problem**: Early versions had issues with tool schema generation for MCP clients.

**Root Cause**: Direct Pydantic schema generation didn't align with MCP protocol expectations.

**Solution**: Integrated with Odoo's `llm_tool` module schema system:

```python
# Current approach in handle_tools_list()
def handle_tools_list(self, request_id, _params):
    """Handle tools/list request using proper MCP types"""
    tools = request.env["llm.tool"].sudo().search([("active", "=", True)])

    mcp_tools = []
    for tool in tools:
        mcp_tool = tool.get_tool_definition()  # Returns MCP SDK Tool object
        if mcp_tool is not None:
            mcp_tools.append(mcp_tool)
```

**Key Insight**: The `llm_tool.get_tool_definition()` method returns proper MCP SDK `Tool` objects with correct schema generation, ensuring consistency across all LLM providers and MCP protocol compliance.

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

## Current Features ✅

### 1. **Authentication & Security**

- ✅ **API Key Authentication**: Integrated with Odoo's `res.users.apikeys` system
- ✅ **User Context Binding**: `request.update_env(user=uid)` for proper user context
- ✅ **Permission Enforcement**: `tool.check_access('read')` respects Odoo ACL rules
- ✅ **No sudo()**: Tool execution runs in authenticated user context
- ✅ **Audit Logging**: User access attempts and tool executions are logged

### 2. **Session Management**

- ✅ **Stateful/Stateless Modes**: Configurable session management
- ✅ **Session Tracking**: Each session has unique ID and lifecycle management
- ✅ **Event Storage**: Comprehensive event tracking for SSE streams
- ✅ **User Activity Logging**: Track which user performed which actions

### 3. **Error Handling**

- ✅ **Structured Exception Hierarchy**: Custom MCP exception classes
- ✅ **JSON-RPC Compliant Errors**: Proper error codes and messages
- ✅ **Detailed Error Responses**: Context-rich error information
- ✅ **Tool Execution Safety**: Graceful handling of tool failures

### 4. **Performance & Scalability**

- ✅ **Component-Based Architecture**: Separation of concerns for maintainability
- ✅ **SSE Streaming**: Non-blocking event-driven responses
- ✅ **Event Replay**: Efficient resumability with minimal resource usage
- ✅ **Session Cleanup**: Proper resource management

## Future Improvements

### High Priority

1. **Streaming Tool Execution (When Needed)**

   ```python
   # For future long-running tools
   @server.call_tool()
   async def bulk_operation_tool(name: str, arguments: dict, ctx: Context):
       await ctx.info("Starting bulk operation...")
       total = arguments.get('count', 100)

       for i in range(total):
           await ctx.report_progress(i, total)
           # Process record

       return f"Processed {total} records"
   ```

2. **Background Job Integration**

   ```python
   # Integrate with Odoo's job queue
   def execute_async_tool(self, tool, arguments):
       job = self.env['queue.job'].with_delay().execute_tool(tool.id, arguments)
       return {"job_id": job.uuid, "status": "queued"}
   ```

3. **Enhanced Monitoring**
   ```python
   # Detailed metrics collection
   def _record_tool_metrics(self, tool_name, execution_time, success):
       env['mcp.tool.metrics'].create({
           'tool_name': tool_name,
           'execution_time_ms': execution_time * 1000,
           'success': success,
           'timestamp': fields.Datetime.now()
       })
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

✅ **Current Security Features**:

- ✅ **API Key Authentication**: Bearer token authentication required for tool execution
- ✅ **User Context Security**: Tools execute in authenticated user context (no sudo)
- ✅ **Permission Enforcement**: Odoo ACL rules are respected for all operations
- ✅ **Audit Trail**: Comprehensive logging of user actions and tool executions
- ✅ **Session Management**: Proper session isolation and cleanup

⚠️ **Remaining Considerations**:

- **Rate Limiting**: Not yet implemented - consider for high-traffic scenarios
- **API Key Rotation**: Plan for regular API key rotation policies
- **Network Security**: Ensure HTTPS in production deployments
- **Tool Permissions**: Review and restrict tool access as needed per user role

## Testing

The module includes a comprehensive curl-based test suite in `curl_test_scripts/`:

### **Quick Testing Commands**

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

### **Server Configuration Modes**

| Mode | Stateless | JSON Response | Resumability | POST | GET | DELETE |
| ---- | --------- | ------------- | ------------ | ---- | --- | ------ |
| 1    | ✅        | ✅            | ❌           | ✅   | ❌  | ❌     |
| 3    | ❌        | ✅            | ❌/✅        | ✅   | ❓  | ✅     |
| 4    | ❌        | ❌            | ❌/✅        | ✅   | ✅  | ✅     |

_Mode 2 (Stateless + SSE) is theoretical and not commonly used_

### **Test Coverage**

- ✅ JSON-RPC 2.0 protocol compliance
- ✅ Authentication (API key validation)
- ✅ Tool discovery and execution
- ✅ Session management across all modes
- ✅ SSE streaming and resumability
- ✅ Event replay functionality
- ✅ Error handling and edge cases

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

### Tool Schema Integration

Schema generation is handled by the `llm_tool` module. If you need custom schema behavior:

```python
# Tool schema is handled by llm_tool module
# Extend the tool's get_tool_definition() method if needed
class CustomTool(models.Model):
    _inherit = 'llm.tool'

    def get_tool_definition(self):
        """Override for custom MCP Tool object generation"""
        # This returns an MCP SDK Tool object
        tool_obj = super().get_tool_definition()
        # Modify the Tool object if needed
        return tool_obj
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

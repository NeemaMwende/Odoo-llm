# MCP Server Refactoring Plan: From Custom Classes to Proper Odoo Patterns

## Executive Summary

Transform the current MCP server implementation from 5+ custom Python classes to proper Odoo model-based architecture while maintaining MCP protocol compliance. The key innovation is using `ir.http` inheritance to create MCP-compatible bearer authentication that works with the protocol's single-route, mixed-auth requirements.

## Current Architecture Problems

### ❌ **Anti-Patterns Identified**
1. **5+ Standalone Python Classes** instead of Odoo models:
   - `MCPSessionManager` (mcp_session_manager.py)
   - `MCPValidator` (mcp_validator.py) 
   - `MCPRequestHandler` (mcp_request_handler.py)
   - `MCPTransport` (mcp_transport.py)
   - `InMemoryEventStore` (event_store.py)

2. **Custom Class Instantiation** in controller:
   ```python
   # Current anti-pattern:
   def __init__(self):
       self.session_manager = MCPSessionManager()      # Not Odoo!
       self.validator = MCPValidator()                 # Not Odoo!
       self.request_handler = MCPRequestHandler(...)   # Not Odoo!
   ```

3. **Business Logic Scattered** across transport, validator, handler layers
4. **No ORM Benefits** - No caching, computed fields, database persistence
5. **Complex Initialization** instead of Odoo's declarative model patterns

### 🚨 **Authentication Conflict**
Odoo's `_auth_method_bearer` doesn't work for MCP because:

```python
# Odoo's bearer auth assumes session consistency:
if request.env.uid and request.env.uid != uid:
    raise AccessDenied("Session user does not match API key user")

# MCP client reality:
# 1. Start anonymous: request.env.uid = public_user.id  
# 2. Use API key for different user: api_key.user_id != public_user.id
# 3. Conflict: AccessDenied exception ❌
```

### 🔒 **MCP Protocol Constraints**
- **Single route required**: `/mcp` (can't split by auth requirements)
- **Mixed authentication**: 
  - Anonymous: `initialize`, `tools/list` methods
  - Authenticated: `tools/call` method
- **Method-based routing**: Authentication decision depends on parsed JSON-RPC method

## Proposed Solution Architecture

### **Phase 1: Add MCP-Compatible Bearer Authentication**

#### **Create `models/ir_http.py`**
```python
from odoo import models
from odoo.http import request
import werkzeug.exceptions
import re

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'
    
    @classmethod
    def authenticate_mcp_bearer_token(cls):
        """MCP-compatible bearer authentication utility method.
        
        Unlike Odoo's _auth_method_bearer, this allows anonymous→authenticated 
        transition required by MCP protocol.
        """
        headers = request.httprequest.headers
        header = headers.get("Authorization")
        
        if not header or not header.lower().startswith("bearer "):
            raise werkzeug.exceptions.Unauthorized(
                "Missing bearer token",
                www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer')
            )
        
        token = header[7:]  # Remove "Bearer " prefix
        
        # Use Odoo's exact same API key validation
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
        if not uid:
            raise werkzeug.exceptions.Unauthorized(
                "Invalid apikey",
                www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer')
            )
        
        # MCP-specific: Allow transition from public user to authenticated user
        public_user_id = request.env.ref('base.public_user').id
        if request.env.uid in (public_user_id, None):
            request.update_env(user=uid)
        elif request.env.uid != uid:
            raise AccessDenied("Session user does not match API key user")
        
        return uid
```

**Key Innovation:** Uses `@classmethod` for request-level authentication utility that can be called conditionally, unlike route-level `auth='bearer'` which applies to all requests.

### **Phase 2: Simplify Controller Architecture**

#### **Ultra-Thin Controller Pattern**
```python
# controllers/mcp_controller.py
from odoo import http
from odoo.http import request
import json

class MCPController(http.Controller):
    
    @http.route('/mcp', type='http', auth='public', methods=['POST'], csrf=False)
    def mcp_endpoint(self):
        """Single MCP endpoint with method-based conditional authentication"""
        
        # Parse method from JSON-RPC request body
        method = self._parse_method_from_request()
        
        # Apply authentication only for tools/call (MCP protocol requirement)
        if method == 'tools/call':
            request.env['ir.http'].authenticate_mcp_bearer_token()
        
        # Route to appropriate model based on method
        if method == 'initialize':
            config = request.env['llm.mcp.server.config'].get_active_config()
            return config.handle_initialize_request()
        elif method == 'tools/list':
            return request.env['llm.tool'].handle_mcp_tools_list()
        elif method == 'tools/call':
            return request.env['llm.tool'].handle_mcp_tools_call()
        else:
            return self._build_error_response(None, f"Unknown method: {method}")
    
    @http.route('/mcp/health', type='http', auth='public', methods=['GET', 'POST'])
    def health_check(self):
        """Health check endpoint"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        return config.get_health_status()
    
    def _parse_method_from_request(self):
        """Extract JSON-RPC method from request body"""
        try:
            raw_body = request.httprequest.get_data(as_text=True)
            if not raw_body.strip():
                return 'initialize'  # Default for empty requests
            
            data = json.loads(raw_body)
            return data.get('method', 'initialize')
        except (json.JSONDecodeError, AttributeError):
            return 'initialize'  # Safe default
    
    def _build_error_response(self, request_id, error):
        """Build error response for unknown methods"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        return config._build_error_response(request_id, error)
```

### **Phase 3: Proper Separation of Concerns**

#### **A. Enhanced Configuration Model** (Only Configuration Logic)
```python
# models/llm_mcp_server_config.py
from odoo import api, fields, models, http
from odoo.http import request
from mcp.types import JSONRPCMessage, JSONRPCResponse, ErrorData
import json

class LLMMCPServerConfig(models.Model):
    _name = "llm.mcp.server.config"
    _inherit = ["mail.thread"]  # Add audit logging
    
    # Change from boolean to selection for future extensibility
    mode = fields.Selection([
        ('stateless', 'Stateless Mode'),
        # ('stateful', 'Stateful Mode'),  # Future implementation
    ], default='stateless', required=True, tracking=True,
       help="Server operation mode")
    
    # Remove session-related boolean fields - simplified to mode selection
    
    def handle_initialize_request(self):
        """Handle MCP initialize request - ONLY config-related logic"""
        try:
            request_data = self._parse_mcp_request()
            
            # Get client info for logging
            client_info = request_data.get('params', {}).get('clientInfo')
            if client_info:
                self._log_client_connection(client_info)
            
            result = {
                "protocolVersion": self.protocol_version,
                "capabilities": self._get_server_capabilities(),
                "serverInfo": {"name": self.name, "version": self.version}
            }
            
            return self._build_json_rpc_response(request_data.get('id'), result=result)
            
        except Exception as e:
            return self._build_error_response(None, error=str(e))
    
    def _parse_mcp_request(self):
        """Parse JSON-RPC request using MCP SDK types"""
        raw_body = request.httprequest.get_data(as_text=True)
        
        if not raw_body.strip():
            return {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}
        
        # Use MCP SDK for proper validation
        message = JSONRPCMessage.model_validate_json(raw_body)
        return message.root.model_dump() if hasattr(message.root, 'model_dump') else {}
    
    def _build_error_response(self, request_id, error):
        """Build error response"""
        return self._build_json_rpc_response(request_id, error=error)
    
    def get_health_status(self):
        """Health check response - only server config info"""
        tools_count = request.env["llm.tool"].search_count([("active", "=", True)])
        
        status = {
            "status": "healthy",
            "server": self.name,
            "version": self.version,
            "mode": self.mode,
            "tools_count": tools_count
        }
        
        return http.Response(
            json.dumps(status, indent=2),
            headers={'Content-Type': 'application/json'}
        )
    
    def _log_client_connection(self, client_info):
        """Log MCP client connection for audit trail"""
        # Uses mail.thread mixin for proper logging
        self.message_post(
            body=f"MCP client connected: {client_info.get('name', 'Unknown')} "
                 f"v{client_info.get('version', 'Unknown')}",
            message_type='comment'
        )
```

#### **B. Enhanced Tool Model** (Tool-Specific Logic)
```python
# models/llm_tool.py - Add MCP-specific methods
from odoo import models
from odoo.http import request
import json

class LLMTool(models.Model):
    _inherit = 'llm.tool'
    
    def handle_mcp_tools_list(self):
        """Handle MCP tools/list request - ONLY tool-related logic"""
        try:
            config = request.env['llm.mcp.server.config'].get_active_config()
            request_data = config._parse_mcp_request()
            
            tools = self.search([("active", "=", True)])
            
            mcp_tools = []
            for tool in tools:
                try:
                    mcp_tool = tool.get_mcp_tool_definition()
                    if mcp_tool:
                        mcp_tools.append(mcp_tool)
                except Exception as e:
                    self._logger.error(f"Error getting tool definition for {tool.name}: {e}")
            
            result = {"tools": mcp_tools}
            return config._build_json_rpc_response(request_data.get('id'), result=result)
            
        except Exception as e:
            config = request.env['llm.mcp.server.config'].get_active_config()
            return config._build_error_response(None, error=str(e))
    
    def handle_mcp_tools_call(self):
        """Handle MCP tools/call request - ONLY tool execution logic"""
        try:
            config = request.env['llm.mcp.server.config'].get_active_config()
            request_data = config._parse_mcp_request()
            
            params = request_data.get('params', {})
            tool_name = params.get('name')
            arguments = params.get('arguments', {})
            
            if not tool_name:
                raise ValueError("Missing tool name")
            
            # Find tool
            tool = self.search([
                ("name", "=", tool_name), ("active", "=", True)
            ], limit=1)
            
            if not tool:
                raise ValueError(f"Tool not found: {tool_name}")
            
            # Check user access (no sudo - respects ACL)
            tool.check_access('read')
            
            # Execute tool safely
            try:
                result = tool.execute(arguments)
                content_text = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)
                
                mcp_result = {
                    "content": [{"type": "text", "text": content_text}],
                    "isError": False
                }
            except Exception as e:
                mcp_result = {
                    "content": [{"type": "text", "text": f"Tool execution failed: {str(e)}"}],
                    "isError": True
                }
            
            return config._build_json_rpc_response(request_data.get('id'), result=mcp_result)
            
        except Exception as e:
            config = request.env['llm.mcp.server.config'].get_active_config()
            return config._build_error_response(None, error=str(e))
    
    def get_mcp_tool_definition(self):
        """Convert Odoo tool to MCP Tool format"""
        from mcp.types import Tool
        
        return Tool(
            name=self.name,
            description=self.description or "",
            inputSchema=self._get_input_schema()
        ).model_dump(exclude_none=True)
    
    def _get_input_schema(self):
        """Get JSON schema for tool inputs"""
        # This would be implemented based on your existing tool schema logic
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    def _get_server_capabilities(self):
        """Get server capabilities based on configuration"""
        from mcp.types import ServerCapabilities, ToolsCapability
        
        capabilities = ServerCapabilities(
            tools=ToolsCapability(listChanged=False)
        )
        return capabilities.model_dump(exclude_none=True)
    
    def _build_json_rpc_response(self, request_id, result=None, error=None):
        """Build JSON-RPC 2.0 response using MCP SDK types"""
        import time
        
        if error:
            from mcp.types import ErrorData, JSONRPCError
            error_data = ErrorData(
                code=-32603,  # Internal error
                message=str(error)
            )
            response = JSONRPCError(
                jsonrpc="2.0",
                id=request_id or int(time.time() * 1000),
                error=error_data
            )
        else:
            from mcp.types import JSONRPCResponse
            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=request_id or int(time.time() * 1000),
                result=result or {}
            )
        
        return http.Response(
            response.model_dump_json(),
            headers={'Content-Type': 'application/json'}
        )
```

### **Phase 4: Cleanup and Removal**

#### **Files to Delete:**
- ❌ `mcp_session_manager.py` - Session logic removed (stateless only)
- ❌ `mcp_validator.py` - Authentication moved to `ir.http` inheritance  
- ❌ `mcp_request_handler.py` - Logic moved to config model
- ❌ `mcp_transport.py` - Response building moved to config model
- ❌ `event_store.py` - Event storage removed (stateless only)

#### **Files to Update:**
- ✅ `models/__init__.py` - Add `from . import ir_http`
- ✅ `controllers/mcp_controller.py` - Simplified to thin delegation layer
- ✅ `models/llm_mcp_server_config.py` - Enhanced with configuration logic only
- ✅ `models/llm_tool.py` - Enhanced with MCP tool-specific methods

### **Phase 5: Configuration Migration**

#### **Update XML Data**
```xml
<!-- data/llm_mcp_server_config.xml -->
<record id="default_mcp_server_config" model="llm.mcp.server.config">
    <field name="name">Odoo LLM MCP Server</field>
    <field name="version">1.0.0</field>
    <field name="protocol_version">2024-11-05</field>
    <field name="active" eval="True" />
    <field name="mode">stateless</field>
</record>
```

## Benefits Analysis

### **Code Reduction**
- **~70% reduction** in custom classes (5 → 0 custom classes)
- **~50% reduction** in total lines of code through proper Odoo patterns
- **Proper separation of concerns**: Config model handles configuration, Tool model handles tool operations

### **Odoo Integration Benefits**
- ✅ **ORM caching** with `@api.depends` and `@tools.ormcache`
- ✅ **Audit logging** via `mail.thread` mixin
- ✅ **Database persistence** for configuration
- ✅ **Access control** integration with Odoo's security model
- ✅ **Standard inheritance** patterns for customization

### **Maintainability Improvements**
- ✅ **Familiar patterns** for Odoo developers
- ✅ **Standard debugging** with Odoo's logging and profiling
- ✅ **Easy extension** through model inheritance
- ✅ **Proper separation** of concerns (auth, business logic, transport)

### **Protocol Compliance Maintained**
- ✅ **MCP protocol compliance** preserved
- ✅ **Anonymous methods** supported (initialize, tools/list)
- ✅ **Authenticated methods** properly secured (tools/call)
- ✅ **Claude Desktop & Letta compatibility** maintained

## Migration Strategy

### **Phase 1: Add Authentication (Non-Breaking)**
1. Create `models/ir_http.py` with MCP bearer auth method
2. Test authentication functionality independently

### **Phase 2: Model Enhancement (Non-Breaking)**  
3. Add configuration logic methods to `llm_mcp_server_config.py`
4. Add tool-specific MCP methods to `llm_tool.py`
5. Test model methods independently with proper separation

### **Phase 3: Controller Simplification (Breaking)**
5. Update controller to use thin delegation pattern
6. Remove custom class instantiation
7. Test full request flow

### **Phase 4: Cleanup (Breaking)**
8. Delete custom classes
9. Update imports and references
10. Run full test suite

### **Phase 5: Configuration Migration**
11. Update XML data structure
12. Migrate existing configurations
13. Update documentation

## Testing Strategy

### **Unit Testing**
```python
# Test authentication in isolation
def test_mcp_bearer_auth():
    # Test with various token scenarios
    
# Test model methods directly  
def test_handle_mcp_request():
    # Test business logic without HTTP layer
```

### **Integration Testing**
- ✅ Maintain existing curl test suite
- ✅ Test with real MCP clients (Claude Desktop, Letta)
- ✅ Verify protocol compliance across all modes

### **Performance Testing**
- ✅ Benchmark before/after refactoring
- ✅ Verify caching improvements
- ✅ Test concurrent request handling

## Success Criteria

- [ ] **Code Reduction**: 70% reduction in custom classes achieved
- [ ] **Protocol Compliance**: All existing curl tests pass
- [ ] **Client Compatibility**: Claude Desktop and Letta integration maintained
- [ ] **Performance**: No regression in request handling speed
- [ ] **Odoo Integration**: Proper use of models, caching, and audit logging
- [ ] **Maintainability**: Standard Odoo patterns used throughout

## Conclusion

This refactoring transforms a custom MCP implementation into a proper Odoo module by:

1. **Leveraging Odoo's authentication system** with MCP-compatible modifications
2. **Using proper model-based architecture** instead of custom classes  
3. **Maintaining protocol compliance** while gaining Odoo integration benefits
4. **Dramatically reducing code complexity** through framework utilization

The key innovation - using `ir.http` inheritance with conditional authentication - solves the fundamental conflict between Odoo's authentication patterns and MCP protocol requirements, enabling both proper Odoo architecture and full MCP compliance.
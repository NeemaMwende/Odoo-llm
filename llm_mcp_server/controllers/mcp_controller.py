import json
import logging
from typing import Any, Optional

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MCPServerController(http.Controller):
    """
    MCP Server Controller for Odoo LLM
    
    Implements the Model Context Protocol (MCP) specification for exposing
    Odoo LLM tools to external systems via HTTP transport.
    
    Protocol: JSON-RPC 2.0 over HTTP
    Transport: streamable_http
    """
    
    # MCP Protocol version we support
    PROTOCOL_VERSION = "2024-11-05"
    
    # Server capabilities
    CAPABILITIES = {
        "tools": {},  # We support tools
        # Could add more capabilities in the future:
        # "prompts": {},
        # "resources": {},
        # "logging": {},
    }
    
    @http.route('/mcp', type='http', auth='none', methods=['POST'], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint handling JSON-RPC 2.0 requests
        
        This endpoint routes MCP protocol messages to appropriate handlers.
        """
        try:
            # Read the raw request body
            raw_body = request.httprequest.get_data(as_text=True)
            _logger.info(f"Raw MCP Request received: {raw_body}")
            
            # Parse JSON from raw body
            if not raw_body.strip():
                params = {}
            else:
                try:
                    params = json.loads(raw_body)
                except json.JSONDecodeError as e:
                    _logger.error(f"Invalid JSON in request: {e}")
                    return self._http_error_response(None, -32700, "Parse error")
            
            _logger.info(f"Parsed MCP Request: {json.dumps(params)}")
            
            # Extract JSON-RPC fields
            jsonrpc = params.get('jsonrpc', '2.0')
            method = params.get('method')
            request_id = params.get('id')
            request_params = params.get('params', {})
            
            # Validate JSON-RPC version
            if jsonrpc != '2.0':
                return self._http_error_response(
                    request_id, 
                    -32600, 
                    f"Invalid JSON-RPC version: {jsonrpc}"
                )
            
            # Handle missing method (likely an initialization probe)
            if not method or method == 'None':
                # Default to initialize if no method specified
                _logger.info("No method specified, defaulting to initialize")
                return self._http_handle_initialize(request_id, request_params)
            
            # Route to appropriate handler based on method
            if method == 'initialize':
                return self._http_handle_initialize(request_id, request_params)
            elif method == 'tools/list':
                return self._http_handle_tools_list(request_id, request_params)
            elif method == 'tools/call':
                return self._http_handle_tools_call(request_id, request_params)
            elif method == 'notifications/initialized':
                # Client notification that initialization is complete
                _logger.info("MCP client initialization complete")
                return http.Response('', status=204)  # No content for notifications
            else:
                return self._http_error_response(
                    request_id,
                    -32601,
                    f"Method not found: {method}"
                )
                
        except Exception as e:
            _logger.exception(f"Error in MCP server: {e}")
            return self._http_error_response(
                None,
                -32603,
                f"Internal error: {str(e)}"
            )
    
    def _http_handle_initialize(self, request_id: Optional[Any], params: dict[str, Any]):
        """
        Handle MCP initialize request with HTTP response
        """
        try:
            _logger.info(f"MCP Initialize request: {params}")
            
            # Extract client info
            client_info = params.get('clientInfo', {})
            client_name = client_info.get('name', 'Unknown')
            client_version = client_info.get('version', 'Unknown')
            
            _logger.info(f"MCP client {client_name} v{client_version}")
            
            # Build JSON-RPC response
            response = {
                "jsonrpc": "2.0",
                "id": request_id if request_id is not None else 1,  # Ensure ID is not None
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": self.CAPABILITIES,
                    "serverInfo": {
                        "name": "Odoo LLM MCP Server",
                        "version": "1.0.0"
                    }
                }
            }
            
            _logger.info("MCP initialization successful")
            return http.Response(
                json.dumps(response),
                headers={'Content-Type': 'application/json'},
                status=200
            )
            
        except Exception as e:
            _logger.exception(f"Error in initialize: {e}")
            return self._http_error_response(request_id, -32603, str(e))
    
    def _http_handle_tools_list(self, request_id: Optional[Any], params: dict[str, Any]):
        """
        Handle tools/list request with HTTP response
        """
        try:
            _logger.info("MCP tools/list request")
            
            # Get all active tools from llm.tool model
            tools_model = request.env['llm.tool'].sudo()
            tools = tools_model.search([('active', '=', True)])
            
            # Convert to MCP tool format
            mcp_tools = []
            for tool in tools:
                tool_def = tool.get_tool_definition()
                mcp_tools.append(tool_def)
            
            _logger.info(f"Returning {len(mcp_tools)} tools")
            
            # Build JSON-RPC response
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": mcp_tools
                }
            }
            
            return http.Response(
                json.dumps(response),
                headers={'Content-Type': 'application/json'},
                status=200
            )
            
        except Exception as e:
            _logger.exception(f"Error listing tools: {e}")
            return self._http_error_response(request_id, -32603, str(e))
    
    def _http_handle_tools_call(self, request_id: Optional[Any], params: dict[str, Any]):
        """
        Handle tools/call request with HTTP response
        """
        try:
            tool_name = params.get('name')
            arguments = params.get('arguments', {})
            
            _logger.info(f"MCP tools/call request for tool: {tool_name}")
            
            if not tool_name:
                return self._http_error_response(request_id, -32602, "Missing tool name")
            
            # Find the tool
            tools_model = request.env['llm.tool'].sudo()
            tool = tools_model.search([
                ('name', '=', tool_name),
                ('active', '=', True)
            ], limit=1)
            
            if not tool:
                return self._http_error_response(
                    request_id,
                    -32602,
                    f"Tool not found: {tool_name}"
                )
            
            # Execute the tool
            try:
                result = tool.execute(arguments)
                
                # Format result for MCP
                if isinstance(result, dict):
                    content_text = json.dumps(result, indent=2)
                else:
                    content_text = str(result)
                
                # Build JSON-RPC response
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": content_text
                            }
                        ],
                        "isError": False
                    }
                }
                
                _logger.info(f"Tool {tool_name} executed successfully")
                return http.Response(
                    json.dumps(response),
                    headers={'Content-Type': 'application/json'},
                    status=200
                )
                
            except Exception as e:
                _logger.exception(f"Error executing tool {tool_name}: {e}")
                
                # Return tool error in result (not as JSON-RPC error)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Tool execution failed: {str(e)}"
                            }
                        ],
                        "isError": True
                    }
                }
                return http.Response(
                    json.dumps(response),
                    headers={'Content-Type': 'application/json'},
                    status=200
                )
                
        except Exception as e:
            _logger.exception(f"Error in tools/call: {e}")
            return self._http_error_response(request_id, -32603, str(e))
    
    def _http_error_response(self, request_id: Optional[Any], code: int, message: str):
        """
        Build a JSON-RPC 2.0 error response as HTTP response
        """
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
        
        return http.Response(
            json.dumps(response),
            headers={'Content-Type': 'application/json'},
            status=200  # JSON-RPC errors are still HTTP 200
        )
    
    @http.route('/mcp/health', type='json', auth='none', methods=['GET', 'POST'], csrf=False)
    def health_check(self, **params):
        """
        Health check endpoint for MCP server
        """
        try:
            # Count available tools
            tools_count = request.env['llm.tool'].sudo().search_count([('active', '=', True)])
            
            return {
                "status": "healthy",
                "server": "Odoo LLM MCP Server",
                "version": "1.0.0",
                "protocol_version": self.PROTOCOL_VERSION,
                "tools_count": tools_count
            }
        except Exception as e:
            _logger.exception(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
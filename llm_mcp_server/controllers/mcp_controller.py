import json
import logging
import time
from typing import Any, Optional

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class JSONRPCErrorCodes:
    """JSON-RPC 2.0 error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom error codes for MCP
    AUTHENTICATION_REQUIRED = -32001
    ACCESS_DENIED = -32003


class MCPConstants:
    """MCP protocol constants"""
    JSON_RPC_VERSION = "2.0"
    CONTENT_TYPE_JSON = "application/json"
    DEFAULT_ARRAY_TYPE = "string"
    HTTP_NO_CONTENT = 204
    HTTP_OK = 200


class MCPServerController(http.Controller):
    """
    MCP Server Controller for Odoo LLM

    Implements the Model Context Protocol (MCP) specification for exposing
    Odoo LLM tools to external systems via HTTP transport.

    Protocol: JSON-RPC 2.0 over HTTP
    Transport: streamable_http
    """

    # Server capabilities
    CAPABILITIES = {
        "tools": {},  # We support tools
        # Could add more capabilities in the future:
        # "prompts": {},
        # "resources": {},
        # "logging": {},
    }

    def _get_server_config(self):
        """Get the active MCP server configuration"""
        config_model = request.env["llm.mcp.server.config"].sudo()
        return config_model.get_active_config()

    def _ensure_valid_id(self, request_id: Optional[Any]) -> int:
        """
        Ensure we have a valid JSON-RPC ID

        Uses the original request ID if present, otherwise generates
        a timestamp-based ID for better uniqueness.
        """
        if request_id is not None:
            return request_id
        return int(time.time() * 1000)  # Milliseconds since epoch

    def _patch_schema_for_openai_compatibility(self, schema_node):
        """
        Recursively patch JSON schema to ensure OpenAI compatibility.

        Specifically ensures 'items' dictionaries have a 'type' defined,
        which OpenAI requires for array types, and 'object' types have
        'additionalProperties' set to false.

        This uses the same logic as the OpenAI provider in llm_openai.
        """
        if not isinstance(schema_node, dict):
            return

        # Ensure object types have additionalProperties: false
        if schema_node.get("type") == "object":
            schema_node["additionalProperties"] = False
        # Fix array items that don't have a type (for existing 'items')
        if "items" in schema_node and isinstance(schema_node["items"], dict):
            items_dict = schema_node["items"]
            if "type" not in items_dict:
                items_dict["type"] = MCPConstants.DEFAULT_ARRAY_TYPE  # Default to string type
            self._patch_schema_for_openai_compatibility(items_dict)

        # Recursively patch properties
        if "properties" in schema_node and isinstance(schema_node["properties"], dict):
            for prop_schema in schema_node["properties"].values():
                self._patch_schema_for_openai_compatibility(prop_schema)

        # Handle schema combiners (anyOf, allOf, oneOf)
        for combiner in ["anyOf", "allOf", "oneOf"]:
            if combiner in schema_node and isinstance(schema_node[combiner], list):
                for sub_schema in schema_node[combiner]:
                    self._patch_schema_for_openai_compatibility(sub_schema)

    @http.route("/mcp", type="http", auth="public", methods=["POST"], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint handling JSON-RPC 2.0 requests

        This endpoint routes MCP protocol messages to appropriate handlers.
        """
        try:
            request_data = self._parse_request()
            return self._route_request(request_data)
        except ValueError as e:
            # Handle parsing and validation errors
            if "Parse error" in str(e):
                return self._http_error_response(None, JSONRPCErrorCodes.PARSE_ERROR, str(e))
            elif "Invalid JSON-RPC version" in str(e):
                return self._http_error_response(None, JSONRPCErrorCodes.INVALID_REQUEST, str(e))
            else:
                return self._http_error_response(None, JSONRPCErrorCodes.INVALID_PARAMS, str(e))
        except Exception as e:
            _logger.exception(f"Error in MCP server: {e}")
            return self._http_error_response(None, JSONRPCErrorCodes.INTERNAL_ERROR, f"Internal error: {str(e)}")

    def _parse_request(self) -> dict:
        """Parse and validate the incoming request"""
        raw_body = request.httprequest.get_data(as_text=True)
        _logger.info(f"MCP Request received: {len(raw_body)} bytes")
        
        if not raw_body.strip():
            return {}
        
        try:
            params = json.loads(raw_body)
            _logger.info(f"Parsed MCP Request: {json.dumps(params)}")
            return params
        except json.JSONDecodeError as e:
            _logger.error(f"Invalid JSON in request: {e}")
            raise ValueError("Parse error") from e

    def _route_request(self, params: dict):
        """Route request to appropriate handler"""
        jsonrpc = params.get("jsonrpc", MCPConstants.JSON_RPC_VERSION)
        method = params.get("method")
        request_id = params.get("id")
        request_params = params.get("params", {})
        
        self._validate_jsonrpc_version(jsonrpc, request_id)
        
        # Handle missing method - Invalid Request per JSON-RPC 2.0 spec
        if not method or method == "None":
            return self._http_error_response(
                request_id, JSONRPCErrorCodes.INVALID_REQUEST, "Missing required 'method' field"
            )
        
        # Route to handlers
        handlers = {
            "initialize": self._http_handle_initialize,
            "tools/list": self._http_handle_tools_list,
            "tools/call": self._http_handle_tools_call,
            "notifications/initialized": self._handle_initialized_notification,
        }
        
        handler = handlers.get(method)
        if not handler:
            return self._http_error_response(
                request_id, JSONRPCErrorCodes.METHOD_NOT_FOUND, f"Method not found: {method}"
            )
        
        # Execute handler with centralized error handling
        try:
            return handler(request_id, request_params)
        except Exception as e:
            _logger.exception(f"Error in {method}: {e}")
            return self._http_error_response(request_id, JSONRPCErrorCodes.INTERNAL_ERROR, str(e))

    def _validate_jsonrpc_version(self, jsonrpc: str, request_id: Optional[Any]):
        """Validate JSON-RPC version"""
        if jsonrpc != MCPConstants.JSON_RPC_VERSION:
            raise ValueError(f"Invalid JSON-RPC version: {jsonrpc}")

    def _handle_initialized_notification(self, request_id: Optional[Any], params: dict):
        """Handle client initialization complete notification"""
        _logger.info("MCP client initialization complete")
        return http.Response("", status=MCPConstants.HTTP_NO_CONTENT)
            
    def _authenticate_request(self):
        """Authenticate MCP request - check if user is logged in"""
        try:
            # Try to get current user from session
            if hasattr(request, 'env') and request.env.user and not request.env.user._is_public():
                user = request.env.user
                _logger.info(f"Authenticated user: {user.login} ({user.name}) - ID: {user.id}")
                return user, None
            else:
                return None, "Authentication required - please provide valid session cookie"
        except Exception as e:
            _logger.warning(f"Authentication error: {e}")
            return None, f"Authentication failed: {str(e)}"
    
    def _build_json_rpc_response(
        self, request_id: Optional[Any], result: dict = None, error: dict = None
    ):
        """
        Build a JSON-RPC 2.0 response (success or error)
        """
        response = {
            "jsonrpc": MCPConstants.JSON_RPC_VERSION,
            "id": self._ensure_valid_id(request_id),
        }

        if error:
            response["error"] = error
        else:
            response["result"] = result or {}

        return response

    def _json_rpc_http_response(
        self, request_id: Optional[Any], result: dict = None, error: dict = None
    ):
        """
        Build and return a JSON-RPC HTTP response
        """
        response = self._build_json_rpc_response(request_id, result, error)
        return http.Response(
            json.dumps(response),
            headers={"Content-Type": MCPConstants.CONTENT_TYPE_JSON},
            status=MCPConstants.HTTP_OK,
        )

    def _http_handle_initialize(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle MCP initialize request"""
        _logger.info(f"MCP Initialize request: {params}")

        # Extract client info
        client_info = params.get("clientInfo", {})
        client_name = client_info.get("name", "Unknown")
        client_version = client_info.get("version", "Unknown")

        _logger.info(f"MCP client {client_name} v{client_version}")

        # Get configuration from database
        config = self._get_server_config()

        result = {
            "protocolVersion": config.protocol_version,
            "capabilities": self.CAPABILITIES,
            "serverInfo": {"name": config.name, "version": config.version},
        }

        _logger.info("MCP initialization successful")
        return self._json_rpc_http_response(request_id, result=result)

    def _http_handle_tools_list(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/list request"""
        _logger.info("MCP tools/list request")

        # Get all active tools from llm.tool model
        tools_model = request.env["llm.tool"].sudo()
        tools = tools_model.search([("active", "=", True)])

        # Convert to MCP tool format
        mcp_tools = []
        for tool in tools:
            tool_def = tool.get_tool_definition()

            # Patch the schema to fix array items (same logic as OpenAI provider)
            if "inputSchema" in tool_def:
                self._patch_schema_for_openai_compatibility(tool_def["inputSchema"])

            mcp_tools.append(tool_def)

        _logger.info(f"Returning {len(mcp_tools)} tools")
        result = {"tools": mcp_tools}
        return self._json_rpc_http_response(request_id, result=result)

    def _http_handle_tools_call(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/call request with authentication"""
        # Check authentication first
        user, auth_error = self._authenticate_request()
        if not user:
            return self._http_error_response(request_id, JSONRPCErrorCodes.AUTHENTICATION_REQUIRED, auth_error)

        try:
            tool_name, arguments = self._extract_tool_params(params, request_id)
            tool = self._get_authorized_tool(tool_name, user, request_id)
            
            if isinstance(tool, http.Response):  # Error response
                return tool
                
            result = self._execute_tool_safely(tool, arguments, user)
            return self._json_rpc_http_response(request_id, result=result)
            
        except ValueError as e:
            return self._http_error_response(request_id, JSONRPCErrorCodes.INVALID_PARAMS, str(e))
        except Exception as e:
            _logger.exception(f"Error in tools/call: {e}")
            return self._http_error_response(request_id, JSONRPCErrorCodes.INTERNAL_ERROR, str(e))

    def _extract_tool_params(self, params: dict, request_id: Optional[Any]):
        """Extract and validate tool parameters"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Missing tool name")
        
        return tool_name, arguments

    def _get_authorized_tool(self, tool_name: str, user, request_id: Optional[Any]):
        """Get tool and verify user access"""
        # Find the tool with user context (not sudo!)
        tool = request.env["llm.tool"].search(
            [("name", "=", tool_name), ("active", "=", True)], limit=1
        )
        
        if not tool:
            return self._http_error_response(
                request_id, JSONRPCErrorCodes.INVALID_PARAMS, f"Tool not found: {tool_name}"
            )
        
        # Check if user has access to this tool
        try:
            tool.check_access('read')
            _logger.info(f"Authenticated tools/call request for tool: {tool_name} by user: {user.login}")
            return tool
        except Exception as e:
            _logger.warning(f"User {user.login} denied access to tool {tool_name}: {e}")
            return self._http_error_response(
                request_id, JSONRPCErrorCodes.ACCESS_DENIED, f"Access denied to tool: {tool_name}"
            )

    def _execute_tool_safely(self, tool, arguments: dict, user) -> dict:
        """Execute tool and format result for MCP"""
        try:
            result = tool.execute(arguments)
            content_text = self._format_tool_result(result)
            
            _logger.info(f"Tool {tool.name} executed successfully by user {user.login}")
            return {
                "content": [{"type": "text", "text": content_text}],
                "isError": False,
            }
            
        except Exception as e:
            _logger.exception(f"Error executing tool {tool.name} for user {user.login}: {e}")
            return {
                "content": [{"type": "text", "text": f"Tool execution failed: {str(e)}"}],
                "isError": True,
            }

    def _format_tool_result(self, result) -> str:
        """Format tool execution result as string"""
        return (
            json.dumps(result, indent=2)
            if isinstance(result, dict)
            else str(result)
        )


    def _http_error_response(self, request_id: Optional[Any], code: int, message: str):
        """Build a JSON-RPC 2.0 error response"""
        error = {"code": code, "message": message}
        return self._json_rpc_http_response(request_id, error=error)

    @http.route(
        "/mcp/health", type="json", auth="none", methods=["GET", "POST"], csrf=False
    )
    def health_check(self, **params):
        """
        Health check endpoint for MCP server
        """
        try:
            # Count available tools
            tools_count = (
                request.env["llm.tool"].sudo().search_count([("active", "=", True)])
            )

            # Get configuration from database
            config = self._get_server_config()

            return {
                "status": "healthy",
                "server": config.name,
                "version": config.version,
                "protocol_version": config.protocol_version,
                "tools_count": tools_count,
            }
        except Exception as e:
            _logger.exception(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

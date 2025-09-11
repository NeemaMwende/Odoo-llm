import json
import logging
import time
from typing import Any, Optional

# MCP SDK imports - required for MCP compliance
from mcp.types import (
    JSONRPCMessage, JSONRPCRequest, JSONRPCNotification, JSONRPCResponse,
    InitializeRequest, CallToolRequest, ListToolsRequest,
    Tool, CallToolResult, TextContent,
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, 
    INVALID_PARAMS, INTERNAL_ERROR
)
from mcp.server.streamable_http import (
    MCP_SESSION_ID_HEADER, MCP_PROTOCOL_VERSION_HEADER,
    CONTENT_TYPE_JSON, CONTENT_TYPE_SSE
)
from pydantic import ValidationError

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


# Custom error codes for MCP authentication (not in standard JSON-RPC spec)
AUTHENTICATION_REQUIRED = -32001
ACCESS_DENIED = -32003

# HTTP status codes
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
                items_dict["type"] = "string"  # Default to string type
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
        # Ensure we always return JSON, even for unhandled exceptions
        try:
            request_data = self._parse_request()
            return self._route_request(request_data)
        except ValueError as e:
            # Handle parsing and validation errors
            _logger.error(f"MCP parsing error: {e}")
            if "Parse error" in str(e):
                return self._http_error_response(None, PARSE_ERROR, str(e))
            elif "Invalid JSON-RPC version" in str(e):
                return self._http_error_response(None, INVALID_REQUEST, str(e))
            else:
                return self._http_error_response(None, INVALID_PARAMS, str(e))
        except Exception as e:
            _logger.exception(f"Unhandled error in MCP server: {e}")
            # Ensure we return JSON even for unexpected errors
            try:
                return self._http_error_response(None, INTERNAL_ERROR, f"Internal error: {str(e)}")
            except Exception as inner_e:
                _logger.error(f"Failed to create error response: {inner_e}")
                # Last resort: manual JSON response
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": INTERNAL_ERROR, "message": "Critical server error"}
                }
                return http.Response(
                    json.dumps(error_response),
                    headers={"Content-Type": CONTENT_TYPE_JSON},
                    status=HTTP_OK
                )

    def _parse_request(self) -> JSONRPCMessage:
        """Parse and validate the incoming request using MCP SDK types"""
        raw_body = request.httprequest.get_data(as_text=True)
        _logger.info(f"MCP Request received: {len(raw_body)} bytes")
        
        if not raw_body.strip():
            # Empty request - create a default message
            return JSONRPCMessage(root=JSONRPCRequest(
                jsonrpc="2.0",
                method="initialize", 
                id=1,
                params={}
            ))
        
        try:
            # Use MCP SDK to parse and validate JSON-RPC message
            message = JSONRPCMessage.model_validate_json(raw_body)
            _logger.info(f"Parsed MCP Message: {message.model_dump_json()}")
            return message
        except json.JSONDecodeError as e:
            _logger.error(f"Invalid JSON in request: {e}")
            raise ValueError("Parse error") from e
        except ValidationError as e:
            _logger.error(f"Invalid JSON-RPC message structure: {e}")
            raise ValueError(f"Invalid JSON-RPC format: {e}") from e

    def _route_request(self, message: JSONRPCMessage):
        """Route request to appropriate handler"""
        request_obj = message.root
        
        # Handle notifications vs requests
        if isinstance(request_obj, JSONRPCNotification):
            return self._handle_notification(request_obj)
        elif isinstance(request_obj, JSONRPCRequest):
            return self._handle_request(request_obj)
        else:
            raise ValueError("Unknown JSON-RPC message type")
            
    def _handle_request(self, request_obj: JSONRPCRequest):
        """Handle JSON-RPC requests"""
        method = request_obj.method
        request_id = request_obj.id
        request_params = request_obj.params or {}
        
        # JSON-RPC version is already validated by MCP SDK
        
        # Method is guaranteed to exist by MCP SDK validation
        if not method:
            return self._http_error_response(
                request_id, INVALID_REQUEST, "Missing required 'method' field"
            )
        
        # Route to handlers
        handlers = {
            "initialize": self._http_handle_initialize,
            "tools/list": self._http_handle_tools_list,
            "tools/call": self._http_handle_tools_call,
        }
        
        handler = handlers.get(method)
        if not handler:
            return self._http_error_response(
                request_id, METHOD_NOT_FOUND, f"Method not found: {method}"
            )
        
        # Execute handler with centralized error handling
        try:
            return handler(request_id, request_params)
        except Exception as e:
            _logger.exception(f"Error in {method}: {e}")
            return self._http_error_response(request_id, INTERNAL_ERROR, str(e))
            
    def _handle_notification(self, notification: JSONRPCNotification):
        """Handle JSON-RPC notifications
        
        According to JSON-RPC spec, notifications should not return responses.
        Return 204 NO CONTENT with no body to comply with the spec.
        """
        if notification.method == "notifications/initialized":
            _logger.info("MCP client initialization complete")
        else:
            _logger.warning(f"Unknown notification method: {notification.method}")
        
        # MCP client always expects valid JSONRPCMessage for application/json responses
        # Even though JSON-RPC spec says notifications have no response,
        # we must return valid JSON-RPC structure using MCP SDK types
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=1,  # Use a dummy ID since None is not allowed
            result={}  # Empty result for notification acknowledgment
        )
        
        return http.Response(
            response.model_dump_json(),
            status=HTTP_OK,
            headers={"Content-Type": CONTENT_TYPE_JSON}
        )

            
    def _extract_api_key(self):
        """Extract API key from Authorization Bearer or X-API-KEY header"""
        import re
        # Check Authorization: Bearer <key>
        header = request.httprequest.headers.get('Authorization')
        if header:
            m = re.match(r"^Bearer\s+(.+)$", header, re.IGNORECASE)
            if m:
                return m.group(1)
        
        # Fallback to X-API-KEY header
        return request.httprequest.headers.get('X-API-KEY')

    def _authenticate_api_key_or_error(self):
        """Validate API key and bind request to corresponding user"""
        token = self._extract_api_key()
        if not token:
            return self._http_error_response(
                None, AUTHENTICATION_REQUIRED,
                "Missing API key in Authorization or X-API-KEY header"
            )
        
        # Validate API key using Odoo's built-in system
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
        if not uid:
            return self._http_error_response(
                None, AUTHENTICATION_REQUIRED,
                "Invalid API key"
            )
        
        # Check for session conflict
        if request.env.uid and request.env.uid != uid:
            return self._http_error_response(
                None, ACCESS_DENIED,
                "Session user does not match API key user"
            )
        
        # Bind request environment to API key owner
        request.update_env(user=uid)
        return None  # Success

    def _authenticate_request(self):
        """Authenticate MCP request - check if user is logged in"""
        try:
            # Try to get current user from session
            if hasattr(request, 'env') and request.env.user and not request.env.user._is_public():
                user = request.env.user
                _logger.info(f"Authenticated user: {user.login} ({user.name}) - ID: {user.id}")
                return user, None
            else:
                raise Exception("User not authenticated")
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
            "jsonrpc": "2.0",
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
            headers={"Content-Type": CONTENT_TYPE_JSON},
            status=HTTP_OK,  # JSON-RPC always returns 200 OK, errors are in the response body
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
            return self._http_error_response(request_id, AUTHENTICATION_REQUIRED, auth_error)

        try:
            tool_name, arguments = self._extract_tool_params(params, request_id)
            tool = self._get_authorized_tool(tool_name, user, request_id)
            
            if isinstance(tool, http.Response):  # Error response
                return tool
                
            result = self._execute_tool_safely(tool, arguments, user)
            return self._json_rpc_http_response(request_id, result=result)
            
        except ValueError as e:
            return self._http_error_response(request_id, INVALID_PARAMS, str(e))
        except Exception as e:
            _logger.exception(f"Error in tools/call: {e}")
            return self._http_error_response(request_id, INTERNAL_ERROR, str(e))

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
                request_id, INVALID_PARAMS, f"Tool not found: {tool_name}"
            )
        
        # Check if user has access to this tool
        try:
            tool.check_access('read')
            _logger.info(f"Authenticated tools/call request for tool: {tool_name} by user: {user.login}")
            return tool
        except Exception as e:
            _logger.warning(f"User {user.login} denied access to tool {tool_name}: {e}")
            return self._http_error_response(
                request_id, ACCESS_DENIED, f"Access denied to tool: {tool_name}"
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

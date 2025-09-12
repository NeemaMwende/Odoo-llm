import json
import logging
import time
from typing import Any, Optional

# MCP SDK imports - required for MCP compliance
from mcp.types import (
    JSONRPCMessage, JSONRPCRequest, JSONRPCNotification, JSONRPCResponse, JSONRPCError,
    InitializeRequest, CallToolRequest, ListToolsRequest, ListToolsResult,
    Tool, CallToolResult, TextContent, ErrorData,
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

    # Methods that require API key authentication
    AUTHENTICATED_METHODS = {
        'tools/call',
        # Add future authenticated methods here
    }

    @property 
    def CAPABILITIES(self):
        """Generate proper MCP ServerCapabilities"""
        from mcp.types import ServerCapabilities, ToolsCapability
        
        return ServerCapabilities(
            tools=ToolsCapability(listChanged=False)
        ).model_dump(exclude_none=True)

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


    @http.route("/mcp", type="http", auth="public", methods=["POST"], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint handling JSON-RPC 2.0 requests

        This endpoint routes MCP protocol messages to appropriate handlers.
        """
        # Ensure we always return JSON, even for unhandled exceptions
        try:
            request_data = self._parse_request()
            _logger.info(f"MCP Request received: {len(request.httprequest.get_data())} bytes")
            _logger.info(f"Raw request data: {request.httprequest.get_data()}")
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
        
        # Check if authentication is required for this method
        auth_required = self._is_authentication_required(method)
        _logger.info(f"Method '{method}' - authentication required: {auth_required}")
        
        if auth_required:
            # Only tools/call requires API key authentication
            self._authenticate_api_key_or_error()
            _logger.info(f"Authentication successful for method '{method}'")
        
        # Route to handlers
        handlers = {
            "initialize": self._http_handle_initialize,
            "tools/list": self._http_handle_tools_list,
            "tools/call": self._http_handle_tools_call,
        }
        
        _logger.info(f"Looking for handler for method: {method}")
        _logger.info(f"Available handlers: {list(handlers.keys())}")
        
        handler = handlers.get(method)
        if not handler:
            return self._http_error_response(
                request_id, METHOD_NOT_FOUND, f"Method not found: {method}"
            )
        
        # Execute handler with centralized error handling
        try:
            _logger.info(f"Calling handler for method: {method}")
            result = handler(request_id, request_params)
            _logger.info(f"Handler returned: {type(result)} - {result}")
            return result
        except Exception as e:
            _logger.exception(f"Error in {method}: {e}")
            return self._http_error_response(request_id, INTERNAL_ERROR, str(e))
            
    def _handle_notification(self, notification: JSONRPCNotification):
        """Handle JSON-RPC notifications
        
        According to MCP specification, notifications should return 202 Accepted with no body.
        https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http
        """
        if notification.method == "notifications/initialized":
            _logger.info("MCP client initialization complete")
        else:
            _logger.warning(f"Unknown notification method: {notification.method}")
        
        # MCP specification: notifications return 202 Accepted with no body
        return http.Response("", status=202, headers={})

            
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
        """Validate API key and bind request to corresponding user. Raises exception on failure."""
        token = self._extract_api_key()
        _logger.info(f"API key authentication - token found: {'Yes' if token else 'No'}")
        if not token:
            _logger.warning("API key authentication failed - no token in headers")
            raise ValueError("Missing API key in Authorization or X-API-KEY header")
        
        # Validate API key using Odoo's built-in system
        # We create keys with scope=None which matches any scope, so we can use 'rpc' for validation
        _logger.info(f"Validating API key: {token[:10]}...{token[-4:] if len(token) > 14 else token}")
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
        _logger.info(f"API key validation result - uid: {uid}")
        if not uid:
            _logger.error(f"Invalid API key provided: {token[:10]}...{token[-4:] if len(token) > 14 else token}")
            raise ValueError("Invalid API key")
        
        # No session conflict check needed - API key authentication takes precedence
        
        # Bind request environment to API key owner
        request.update_env(user=uid)
        _logger.info(f"Successfully authenticated and bound to user {uid}")
        # Success - no exception raised

    def _is_authentication_required(self, method: str) -> bool:
        """Determine if API key authentication is required for this method"""
        return method in self.AUTHENTICATED_METHODS
    
    def _build_json_rpc_response(
        self, request_id: Optional[Any], result: dict = None, error: dict = None
    ):
        """
        Build a JSON-RPC 2.0 response using proper MCP SDK Pydantic models
        """
        if error:
            # For error responses, use JSONRPCError with ErrorData
            error_data = ErrorData(
                code=error.get("code", INTERNAL_ERROR),
                message=error.get("message", "Internal error"),
                data=error.get("data")
            )
            response = JSONRPCError(
                jsonrpc="2.0",
                id=self._ensure_valid_id(request_id),
                error=error_data,
            )
        else:
            # For success responses, use JSONRPCResponse
            response = JSONRPCResponse(
                jsonrpc="2.0", 
                id=self._ensure_valid_id(request_id),
                result=result or {},
            )
        
        return response

    def _json_rpc_http_response(
        self, request_id: Optional[Any], result: dict = None, error: dict = None
    ):
        """
        Build and return a JSON-RPC HTTP response using MCP SDK Pydantic model
        """
        response_model = self._build_json_rpc_response(request_id, result, error)
        return http.Response(
            response_model.model_dump_json(),
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

        capabilities = self.CAPABILITIES
        result = {
            "protocolVersion": config.protocol_version,
            "capabilities": capabilities,
            "serverInfo": {"name": config.name, "version": config.version},
        }

        _logger.info(f"MCP initialization successful with capabilities: {capabilities}")
        _logger.info(f"Full initialize result: {result}")
        return self._json_rpc_http_response(request_id, result=result)

    def _http_handle_tools_list(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/list request using proper MCP types"""
        _logger.info("MCP tools/list request")

        # Get all active tools from llm.tool model
        tools_model = request.env["llm.tool"].sudo()
        tools = tools_model.search([("active", "=", True)])

        # Get MCP Tool objects directly
        mcp_tools = []
        for tool in tools:
            try:
                mcp_tool = tool.get_tool_definition()  # This returns a Tool object
                if mcp_tool is not None:
                    mcp_tools.append(mcp_tool)
                    _logger.info(f"Added tool: {mcp_tool.name}")
                else:
                    _logger.warning(f"Tool {tool.name} returned None from get_tool_definition()")
            except Exception as e:
                _logger.error(f"Error getting tool definition for {tool.name}: {e}")
                continue

        _logger.info(f"Total tools collected: {len(mcp_tools)}")
        
        # Create proper MCP response using ListToolsResult
        result = ListToolsResult(tools=mcp_tools)
        
        _logger.info(f"Created ListToolsResult with {len(result.tools)} tools")
        
        # Use exclude_none=True to omit null fields that Letta doesn't expect
        result_data = result.model_dump(exclude_none=True)
        _logger.info(f"Result data: {result_data}")
        
        return self._json_rpc_http_response(request_id, result=result_data)

    def _http_handle_tools_call(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/call request (authentication already handled centrally)"""
        try:
            tool_name, arguments = self._extract_tool_params(params, request_id)
            tool = self._get_authorized_tool(tool_name, request.env.user, request_id)
            
            if isinstance(tool, http.Response):  # Error response
                return tool
                
            result = self._execute_tool_safely(tool, arguments, request.env.user)
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

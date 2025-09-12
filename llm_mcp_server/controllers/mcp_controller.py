import json
import logging
import time
from typing import Any, Optional

from mcp.server.streamable_http import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
    MCP_PROTOCOL_VERSION_HEADER,
    MCP_SESSION_ID_HEADER,
)

# MCP SDK imports - required for MCP compliance
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    CallToolRequest,
    CallToolResult,
    ErrorData,
    InitializeRequest,
    JSONRPCError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    ListToolsRequest,
    ListToolsResult,
    TextContent,
    Tool,
)
from pydantic import ValidationError

from odoo import http
from odoo.http import request

from .event_store import InMemoryEventStore

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
    
    # Class-level event store for resumability (shared across all requests)
    _event_store = None

    @classmethod
    def get_event_store(cls):
        """Get or create the shared event store instance"""
        if cls._event_store is None:
            cls._event_store = InMemoryEventStore(max_events_per_stream=100)
        return cls._event_store

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


    @http.route("/mcp", type="http", auth="public", methods=["GET", "POST", "DELETE"], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint handling multiple HTTP methods per MCP spec

        - POST: JSON-RPC 2.0 requests
        - GET: SSE streaming for stateful mode  
        - DELETE: Session termination
        """
        # Route based on HTTP method
        method = request.httprequest.method
        
        try:
            if method == "POST":
                return self._handle_post_request()
            elif method == "GET":
                return self._handle_get_request()
            elif method == "DELETE":
                return self._handle_delete_request()
            else:
                return self._http_error_response(None, METHOD_NOT_FOUND, f"Method {method} not supported")
                
        except Exception as e:
            _logger.exception(f"Unhandled error in MCP server: {e}")
            # Ensure we return appropriate response even for unexpected errors
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
        
        if auth_required:
            # Only tools/call requires API key authentication
            self._authenticate_api_key_or_error()
        
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
            result = handler(request_id, request_params)
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
        if not token:
            raise ValueError("Missing API key in Authorization or X-API-KEY header")
        
        # Validate API key using Odoo's built-in system
        # We create keys with scope=None which matches any scope, so we can use 'rpc' for validation
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
        if not uid:
            raise ValueError("Invalid API key")
        
        # Bind request environment to API key owner
        request.update_env(user=uid)
        # Success - no exception raised

    def _is_authentication_required(self, method: str) -> bool:
        """Determine if API key authentication is required for this method"""
        return method in self.AUTHENTICATED_METHODS
    
    def _get_session_id(self):
        """Get session ID from MCP header or Odoo session"""
        # Check for explicit MCP session ID header first
        mcp_session_id = request.httprequest.headers.get(MCP_SESSION_ID_HEADER)
        if mcp_session_id:
            return mcp_session_id
        
        # Fallback to Odoo session ID (most common case)
        return request.session.sid
    
    def _handle_post_request(self):
        """Handle POST requests - JSON-RPC 2.0 messages"""
        try:
            # Validate protocol headers
            accept_error = self._validate_accept_headers('POST')
            if accept_error:
                return accept_error
            
            content_type_error = self._validate_content_type('POST')
            if content_type_error:
                return content_type_error
            
            protocol_error = self._validate_protocol_version()
            if protocol_error:
                return protocol_error
            
            # Get configuration to check mode
            config = self._get_server_config()
            
            if config.stateless_mode:
                return self._handle_stateless_post()
            else:
                return self._handle_stateful_post()
                
        except ValueError as e:
            # Handle parsing and validation errors
            _logger.error(f"MCP POST parsing error: {e}")
            if "Parse error" in str(e):
                return self._http_error_response(None, PARSE_ERROR, str(e))
            elif "Invalid JSON-RPC version" in str(e):
                return self._http_error_response(None, INVALID_REQUEST, str(e))
            else:
                return self._http_error_response(None, INVALID_PARAMS, str(e))
    
    def _handle_get_request(self):
        """Handle GET requests - SSE streaming for stateful mode"""
        # Validate protocol headers
        accept_error = self._validate_accept_headers('GET')
        if accept_error:
            return accept_error
        
        protocol_error = self._validate_protocol_version()
        if protocol_error:
            return protocol_error
            
        config = self._get_server_config()
        
        if config.stateless_mode:
            return self._http_error_response(None, METHOD_NOT_FOUND, "GET not supported in stateless mode")
        
        return self._handle_sse_stream()
    
    def _handle_delete_request(self):
        """Handle DELETE requests - Session termination"""
        config = self._get_server_config()
        
        if config.stateless_mode:
            return self._http_error_response(None, METHOD_NOT_FOUND, "DELETE not supported in stateless mode")
        
        return self._handle_session_delete()
    
    def _handle_stateless_post(self):
        """Handle POST in stateless mode - direct JSON responses"""
        request_data = self._parse_request()
        return self._route_request(request_data)
    
    def _handle_stateful_post(self):
        """Handle POST in stateful mode - always return JSON responses"""
        # POST requests always return direct JSON responses per MCP spec
        # SSE streaming is handled by GET requests in _handle_sse_stream()
        request_data = self._parse_request()
        return self._route_request(request_data)
    
    def _handle_sse_stream(self):
        """Handle SSE streaming with resumability support"""
        session_id = self._get_session_id()
        
        # Validate session ID format
        if not self._validate_session_id_format(session_id):
            return self._http_error_response(None, 400, "Invalid session ID format")
        
        # Handle resumability - check for Last-Event-ID header
        last_event_id = request.httprequest.headers.get('last-event-id')
        if last_event_id:
            return self._replay_events(session_id, last_event_id)
        
        # Get event store
        event_store = self.get_event_store()
        
        def generate():
            try:
                # Send connection established event
                connection_msg = JSONRPCResponse(
                    jsonrpc="2.0",
                    id=None,
                    result={"type": "connected", "timestamp": time.time()}
                )
                
                # Store event if resumability enabled
                config = self._get_server_config()
                if config.enable_resumability:
                    # Use asyncio to call async method
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    event_id = loop.run_until_complete(
                        event_store.store_event(session_id, connection_msg)
                    )
                    loop.close()
                    yield f"event: connected\ndata: {connection_msg.model_dump_json()}\nid: {event_id}\n\n"
                else:
                    yield f"event: connected\ndata: {connection_msg.model_dump_json()}\n\n"
                
                # Keep connection alive with periodic pings
                ping_count = 0
                while True:
                    try:
                        # Send periodic ping to keep connection alive
                        ping_count += 1
                        ping_msg = JSONRPCResponse(
                            jsonrpc="2.0",
                            id=None,
                            result={
                                "type": "ping", 
                                "count": ping_count,
                                "timestamp": time.time()
                            }
                        )
                        
                        if config.enable_resumability:
                            import asyncio
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            event_id = loop.run_until_complete(
                                event_store.store_event(session_id, ping_msg)
                            )
                            loop.close()
                            yield f"event: ping\ndata: {ping_msg.model_dump_json()}\nid: {event_id}\n\n"
                        else:
                            yield f"event: ping\ndata: {ping_msg.model_dump_json()}\n\n"
                        
                        # Wait before next ping (30 seconds)
                        time.sleep(30)
                        
                    except GeneratorExit:
                        _logger.info(f"SSE stream closed by client for session {session_id}")
                        break
                    except Exception as e:
                        _logger.error(f"Error in SSE stream for session {session_id}: {e}")
                        break
                
            except Exception as e:
                _logger.error(f"Error in SSE generator: {e}")
        
        return http.Response(
            generate(),
            content_type=CONTENT_TYPE_SSE,
            headers={
                'Cache-Control': 'no-cache, no-transform',
                'Connection': 'keep-alive',
                MCP_SESSION_ID_HEADER: session_id
            }
        )
    
    def _handle_session_delete(self):
        """Handle session deletion"""
        try:
            session_id = self._get_session_id()
            
            # For in-memory implementation, we could clear the stream from event store
            # But since it's in-memory, this is mainly for protocol compliance
            _logger.info(f"Session {session_id} deletion requested")
            
            return http.Response("", status=HTTP_NO_CONTENT)
            
        except Exception as e:
            _logger.error(f"Error deleting session: {e}")
            return self._http_error_response(None, INTERNAL_ERROR, f"Failed to delete session: {str(e)}")
    
    def _validate_accept_headers(self, method: str):
        """Validate Accept headers per MCP specification"""
        accept_header = request.httprequest.headers.get('accept', '')
        
        if method == 'POST':
            # POST MUST accept BOTH application/json AND text/event-stream
            required_types = ['application/json', 'text/event-stream']
            
            # Check if accept header contains both required types or is wildcard
            if accept_header == '*/*' or 'application/*' in accept_header:
                return None  # Wildcard accepts everything
                
            missing_types = []
            for required_type in required_types:
                if required_type not in accept_header:
                    missing_types.append(required_type)
            
            if missing_types:
                return self._http_error_response(
                    None, 406, 
                    f"POST requests must accept both application/json and text/event-stream. Missing: {', '.join(missing_types)}"
                )
                
        elif method == 'GET':
            # GET MUST accept text/event-stream for SSE
            if 'text/event-stream' not in accept_header and accept_header not in ['*/*', 'text/*']:
                return self._http_error_response(
                    None, 406,
                    "GET requests must accept text/event-stream for SSE streaming"
                )
                
        return None  # Valid headers
    
    def _validate_content_type(self, method: str):
        """Validate Content-Type headers per MCP specification"""
        if method != 'POST':
            return None  # Only validate POST content-type
        
        content_type = request.httprequest.headers.get('content-type', '')
        
        if not content_type.startswith('application/json'):
            return self._http_error_response(
                None, 415,
                "POST requests must have Content-Type: application/json"
            )
        
        return None  # Valid content-type
    
    def _validate_protocol_version(self):
        """Validate MCP protocol version header"""
        protocol_version = request.httprequest.headers.get(MCP_PROTOCOL_VERSION_HEADER, '')
        config = self._get_server_config()
        
        if protocol_version and protocol_version != config.protocol_version:
            _logger.warning(f"Client protocol version {protocol_version} differs from server {config.protocol_version}")
            # This is a warning, not an error - servers should be backwards compatible
        
        return None  # Protocol version validation is informational
    
    def _validate_session_id_format(self, session_id: str) -> bool:
        """Validate session ID format - Odoo session IDs are always valid"""
        # Odoo generates proper session IDs, so this is mainly for external validation
        if not session_id or len(session_id) < 10:
            return False
        return True
    
    def _extract_session_id(self):
        """Extract session ID from MCP-Session-Id header or use Odoo session"""
        # Check for explicit MCP session ID header
        mcp_session_id = request.httprequest.headers.get(MCP_SESSION_ID_HEADER)
        
        if mcp_session_id:
            return mcp_session_id
        
        # Fallback to Odoo session ID
        return request.session.sid
    
    def _replay_events(self, session_id: str, last_event_id: str):
        """Replay events after specified event ID for resumability"""
        try:
            event_store = self.get_event_store()
            
            def generate():
                try:
                    # Send reconnection event
                    reconnect_msg = JSONRPCResponse(
                        jsonrpc="2.0",
                        id=None,
                        result={"type": "reconnected", "resumed_from": last_event_id}
                    )
                    yield f"event: reconnected\ndata: {reconnect_msg.model_dump_json()}\n\n"
                    
                    # Define callback for replaying events
                    async def replay_callback(event_message):
                        event_data = event_message.message.model_dump_json()
                        yield f"event: message\ndata: {event_data}\nid: {event_message.event_id}\n\n"
                    
                    # Replay missed events using the event store
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    resumed_stream_id = loop.run_until_complete(
                        event_store.replay_events_after(last_event_id, replay_callback)
                    )
                    loop.close()
                    
                    if resumed_stream_id:
                        _logger.info(f"Resumed stream {resumed_stream_id} from event {last_event_id}")
                    
                    # Continue with live streaming (simplified)
                    config = self._get_server_config()
                    ping_count = 0
                    while True:
                        try:
                            ping_count += 1
                            ping_msg = JSONRPCResponse(
                                jsonrpc="2.0",
                                id=None,
                                result={
                                    "type": "ping", 
                                    "count": ping_count,
                                    "timestamp": time.time()
                                }
                            )
                            
                            if config.enable_resumability:
                                import asyncio
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                event_id = loop.run_until_complete(
                                    event_store.store_event(session_id, ping_msg)
                                )
                                loop.close()
                                yield f"event: ping\ndata: {ping_msg.model_dump_json()}\nid: {event_id}\n\n"
                            else:
                                yield f"event: ping\ndata: {ping_msg.model_dump_json()}\n\n"
                            
                            time.sleep(30)
                            
                        except GeneratorExit:
                            _logger.info(f"Resumed SSE stream closed by client for session {session_id}")
                            break
                        except Exception as e:
                            _logger.error(f"Error in resumed SSE stream for session {session_id}: {e}")
                            break
                    
                except Exception as e:
                    _logger.error(f"Error in replay generator: {e}")
            
            return http.Response(
                generate(),
                content_type=CONTENT_TYPE_SSE,
                headers={
                    'Cache-Control': 'no-cache, no-transform',
                    'Connection': 'keep-alive',
                    MCP_SESSION_ID_HEADER: session_id
                }
            )
            
        except Exception as e:
            _logger.error(f"Failed to replay events: {e}")
            return self._http_error_response(None, INTERNAL_ERROR, f"Failed to resume stream: {str(e)}")
    
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
        # Get session ID
        session_id = self._get_session_id()
        
        # Store client information if provided (could be stored in event store as metadata)
        if params.get("clientInfo"):
            client_info = params["clientInfo"]
            _logger.info(f"MCP client connected: {client_info.get('name')} v{client_info.get('version')}")
        
        # Get configuration from database
        config = self._get_server_config()

        capabilities = self.CAPABILITIES
        result = {
            "protocolVersion": config.protocol_version,
            "capabilities": capabilities,
            "serverInfo": {"name": config.name, "version": config.version},
            # Return session ID for MCP protocol compliance
            "sessionId": session_id
        }

        return self._json_rpc_http_response(request_id, result=result)

    def _http_handle_tools_list(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/list request using proper MCP types"""
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
            except Exception as e:
                _logger.error(f"Error getting tool definition for {tool.name}: {e}")
                continue
        
        # Create proper MCP response using ListToolsResult
        result = ListToolsResult(tools=mcp_tools)
        
        # Use exclude_none=True to omit null fields that Letta doesn't expect
        result_data = result.model_dump(exclude_none=True)
        
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

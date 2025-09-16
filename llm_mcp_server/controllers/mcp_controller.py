"""
MCP Server Controller for Odoo

Ultra-thin HTTP controller that routes requests to appropriate Odoo models
following proper separation of concerns.
"""

import json
import logging
import time
from http import HTTPStatus
from typing import Optional, Union

from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    ErrorData,
    InitializeResult,
    JSONRPCError,
    JSONRPCResponse,
)
from pydantic import BaseModel

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# MCP SDK Constants
CONTENT_TYPE_JSON = "application/json"
MCP_SESSION_ID_HEADER = "Mcp-Session-Id"
MCP_PROTOCOL_VERSION_HEADER = "Mcp-Protocol-Version"


class MCPInitializeResponse(BaseModel):
    """Wrapper for MCP initialize method response"""

    result: InitializeResult
    session_id: Optional[str] = None


def requires_bearer_auth(handler_func):
    """Decorator that applies MCP-compatible bearer authentication"""

    def wrapper(self, *args, **kwargs):
        # Clean up the public uid and use built-in _auth_method_bearer
        request.update_env(user=False)
        request.env["ir.http"]._auth_method_bearer()

        # Authentication succeeded - proceed with handler
        return handler_func(self, *args, **kwargs)

    return wrapper


# MCP Exception Classes
class MCPError(Exception):
    """Base MCP exception with JSON-RPC error code"""

    def __init__(self, message: str, code: int = INTERNAL_ERROR):
        super().__init__(message)
        self.code = code
        self.message = message


class MCPParseError(MCPError):
    """JSON parsing error"""

    def __init__(self, message: str = "Parse error"):
        super().__init__(message, PARSE_ERROR)


class MCPInvalidRequestError(MCPError):
    """Invalid JSON-RPC request structure"""

    def __init__(self, message: str = "Invalid JSON-RPC request"):
        super().__init__(message, INVALID_REQUEST)


class MCPMethodNotFoundError(MCPError):
    """JSON-RPC method not found"""

    def __init__(self, method: str):
        message = f"Method not found: {method}"
        super().__init__(message, METHOD_NOT_FOUND)


class MCPInvalidParamsError(MCPError):
    """Invalid method parameters"""

    def __init__(self, message: str = "Invalid parameters"):
        super().__init__(message, INVALID_PARAMS)


class MCPController(http.Controller):
    """
    Ultra-thin MCP Server Controller following Odoo best practices.

    This controller delegates all business logic to Odoo models:
    - Config model handles initialize and server configuration
    - Tool model handles tools/list and tools/call
    """

    @http.route(
        "/mcp", type="http", auth="public", methods=["POST", "OPTIONS"], csrf=False
    )
    def mcp_endpoint(self):
        """MCP endpoint for JSON-RPC methods"""
        request_id = None

        # Parse session ID once
        session_id = request.httprequest.headers.get("mcp-session-id")

        try:
            # Parse full JSON-RPC request - controller handles all protocol details
            request_data = self._parse_mcp_request()
            method = request_data["method"]
            request_id = request_data.get("id")
            params = request_data.get("params", {})

            # Check if method handler exists first (before session validation)
            if not self._is_callable(method):
                raise MCPMethodNotFoundError(method)

            # Validate session requirements
            session_error = self._validate_session_requirements(method, session_id)
            if session_error:
                return session_error

            # Dispatch to appropriate handler
            dispatch_result = self._dispatch(method, params, request_id, session_id)

            # Handle special case for notifications that return HTTP Response directly
            if isinstance(dispatch_result, http.Response):
                return dispatch_result

            # Handle MCPInitializeResponse wrapper (from initialize method)
            if isinstance(dispatch_result, MCPInitializeResponse):
                result = dispatch_result.result
                response_session_id = dispatch_result.session_id
            else:
                # All other methods return result directly
                result = dispatch_result
                response_session_id = None

            # Build JSON-RPC success response
            # Convert pydantic result object to dict for JSON-RPC response
            if hasattr(result, "model_dump"):
                result_data = result.model_dump(exclude_none=True)
            else:
                result_data = result or {}

            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=request_id if request_id is not None else int(time.time() * 1000),
                result=result_data,
            )

            return self._create_json_response(
                response_message=response, session_id=response_session_id
            )

        except MCPError as e:
            # Handle all MCP-specific errors with their proper error codes
            error_response = JSONRPCError(
                jsonrpc="2.0",
                id=request_id if request_id is not None else int(time.time() * 1000),
                error=ErrorData(code=e.code, message=e.message),
            )
            return self._create_json_response(response_message=error_response)
        except Exception:
            # Handle unexpected errors
            _logger.exception("Unexpected error in MCP endpoint")
            return self._create_error_response(
                error_message="Internal server error",
                status_code=HTTPStatus.OK,  # JSON-RPC always uses HTTPStatus.OK, error is in response body
                error_code=INTERNAL_ERROR,
                request_id=request_id,
            )

    @http.route("/mcp", type="http", auth="bearer", methods=["DELETE"], csrf=False)
    def mcp_delete_session(self):
        """MCP endpoint for session termination"""
        return self._handle_delete_session()

    def _parse_mcp_request(self):
        """Parse full MCP JSON-RPC request"""
        raw_body = request.httprequest.get_data(as_text=True)

        if not raw_body.strip():
            raise MCPInvalidRequestError("Empty request body")

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as e:
            raise MCPParseError(f"Invalid JSON: {str(e)}") from e

        if "method" not in data:
            raise MCPInvalidRequestError("Missing 'method' in JSON-RPC request")

        # Validate basic JSON-RPC 2.0 structure
        if data.get("jsonrpc") != "2.0":
            raise MCPInvalidRequestError("Invalid JSON-RPC version, must be '2.0'")

        return data

    def _get_session(self, session_id):
        return request.env["llm.mcp.session"].get_session(session_id)

    def _validate_session_requirements(self, method_name, session_id):
        """Validate session requirements based on server mode and method"""
        config = request.env["llm.mcp.server.config"].get_active_config()

        # For stateless mode, no session validation needed
        if config.mode == "stateless":
            return None

        # For stateful mode, check session requirements
        if method_name not in ["initialize", "ping", "notifications/initialized"]:
            if not session_id:
                return http.Response(
                    json.dumps({"error": "Missing mcp-session-id header"}),
                    headers={"Content-Type": "application/json"},
                    status=HTTPStatus.BAD_REQUEST,
                )

            session = request.env["llm.mcp.session"].get_session(session_id)
            if not session:
                return http.Response(
                    json.dumps({"error": "Session not found"}),
                    headers={"Content-Type": "application/json"},
                    status=HTTPStatus.NOT_FOUND,
                )

            # Check if method is allowed in current session state
            if not session.is_method_allowed(method_name):
                return http.Response(
                    json.dumps(
                        {
                            "error": "Bad Request",
                            "message": f"Method '{method_name}' not allowed in state '{session.state}'",
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                    status=HTTPStatus.BAD_REQUEST,
                )

        return None  # No error

    def _validate_protocol_version(self, requested_version, config):
        """Validate protocol version following MCP SDK pattern"""
        # If no version requested, use default (latest)
        if not requested_version:
            return config.get_default_protocol_version(), None

        # Validate requested version
        if not config.is_protocol_version_supported(requested_version):
            supported_versions = config.get_supported_versions_string()
            error_response = self._create_error_response(
                error_message=f"Bad Request: Unsupported protocol version: {requested_version}. "
                f"Supported versions: {supported_versions}",
                status_code=HTTPStatus.BAD_REQUEST,
                error_code=INVALID_REQUEST,
            )
            return None, error_response

        return requested_version, None  # No error

    def _handle_delete_session(self):
        """Handle DELETE request for session termination"""
        session_id = request.httprequest.headers.get("mcp-session-id")

        if not session_id:
            return http.Response(
                "Missing mcp-session-id header",
                status=HTTPStatus.BAD_REQUEST,  # Bad Request
            )

        # Find session using the model's get_session method
        session = request.env["llm.mcp.session"].get_session(session_id)

        if not session:
            return http.Response(
                "Session not found",
                status=HTTPStatus.NOT_FOUND,  # Not Found
            )

        session.terminate()
        return http.Response("", status=HTTPStatus.NO_CONTENT)  # No Content

    # MCP Method Handlers
    def _mcp_initialize(self, params, request_id, session_id):
        """Handle initialize method with protocol version validation"""
        config = request.env["llm.mcp.server.config"].get_active_config()

        # Extract protocol version from headers or params
        requested_version = request.httprequest.headers.get(
            MCP_PROTOCOL_VERSION_HEADER
        ) or params.get("protocolVersion")

        # Validate protocol version (use default if missing)
        negotiated_version, error_response = self._validate_protocol_version(
            requested_version, config
        )
        if error_response:
            return error_response

        # Get server response using the negotiated version
        result = config.handle_initialize_request(
            client_info=params.get("clientInfo"), protocol_version=negotiated_version
        )
        # For stateful mode, create new session
        if config.mode == "stateful":
            session = request.env["llm.mcp.session"].create_new_session()

            # Store client information in session
            if params.get("clientInfo"):
                session.client_info = params["clientInfo"]
            if params.get("capabilities"):
                session.client_capabilities = params["capabilities"]
            # Store the negotiated protocol version
            session.protocol_version = negotiated_version

            # Transition to initializing state
            session.transition_to("initializing")

            # Return wrapped response with session_id
            return MCPInitializeResponse(result=result, session_id=session.session_id)

        # For stateless mode, return wrapped response without session_id
        return MCPInitializeResponse(result=result)

    def _mcp_notifications_initialized(self, params, request_id, session_id):
        """Handle notifications/initialized method"""
        # Get session and transition to initialized state
        if session_id:
            session = request.env["llm.mcp.session"].get_session(session_id)

            if session and session.state == "initializing":
                session.transition_to("initialized")
                # Force immediate commit so concurrent requests see the updated state
                session._cr.commit()

        return http.Response(
            "", headers={"Content-Type": "application/json"}, status=HTTPStatus.ACCEPTED
        )

    def _mcp_ping(self, params, request_id, session_id):
        """Handle ping method"""
        return {}

    def _mcp_tools_list(self, params, request_id, session_id):
        """Handle tools/list method"""
        return request.env["llm.tool"].get_mcp_tools_list(params=params)

    @requires_bearer_auth
    def _mcp_tools_call(self, params, request_id, session_id):
        """Handle tools/call method"""
        # Update session user_id if we have a session and authenticated user
        if session_id and request.env.user and not request.env.user._is_public():
            session = request.env["llm.mcp.session"].get_session(session_id)
            if session and not session.user_id:
                session.user_id = request.env.user.id

        return request.env["llm.tool"].execute_mcp_tool(params=params)

    def _is_callable(self, method_name):
        """Check if method handler exists"""
        handler_name = f"_mcp_{method_name.replace('/', '_').replace('-', '_')}"
        return hasattr(self, handler_name) and callable(getattr(self, handler_name))

    def _dispatch(self, method_name, params, request_id, session_id):
        """Dispatch MCP method to appropriate handler"""
        # Transform method name to handler name
        handler_name = f"_mcp_{method_name.replace('/', '_').replace('-', '_')}"

        # Get handler method
        handler = getattr(self, handler_name, None)
        if not handler:
            raise MCPMethodNotFoundError(method_name)

        # Call handler
        return handler(params, request_id, session_id)

    def _create_json_response(
        self,
        response_message: Union[JSONRPCResponse, JSONRPCError, None],
        status_code: HTTPStatus = HTTPStatus.OK,
        headers: Optional[dict[str, str]] = None,
        session_id: Optional[str] = None,
    ) -> http.Response:
        """Create a JSON response from a JSONRPCMessage following MCP SDK patterns

        Args:
            response_message: The JSON-RPC response message
            status_code: HTTP status code (defaults to HTTPStatus.OK)
            headers: Additional headers to include
            session_id: Optional session ID for Mcp-Session-Id header
        """
        response_headers = {"Content-Type": CONTENT_TYPE_JSON}
        if headers:
            response_headers.update(headers)

        if session_id:
            response_headers[MCP_SESSION_ID_HEADER] = session_id

        response_json = (
            response_message.model_dump_json(by_alias=True, exclude_none=True)
            if response_message
            else None
        )

        return http.Response(
            response_json, headers=response_headers, status=status_code
        )

    def _create_error_response(
        self,
        error_message: str,
        status_code: HTTPStatus,
        error_code: int = INVALID_REQUEST,
        headers: Optional[dict[str, str]] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> http.Response:
        """Create an error response with a simple string message following MCP SDK patterns

        Args:
            error_message: The error message to include
            status_code: HTTP status code
            error_code: JSON-RPC error code (defaults to INVALID_REQUEST)
            headers: Additional headers to include
            session_id: Optional session ID for Mcp-Session-Id header
            request_id: Optional request ID for correlation
        """
        response_headers = {"Content-Type": CONTENT_TYPE_JSON}
        if headers:
            response_headers.update(headers)

        if session_id:
            response_headers[MCP_SESSION_ID_HEADER] = session_id

        # Return a properly formatted JSON error response
        error_response = JSONRPCError(
            jsonrpc="2.0",
            id=request_id if request_id is not None else "server-error",
            error=ErrorData(
                code=error_code,
                message=error_message,
            ),
        )

        return http.Response(
            error_response.model_dump_json(by_alias=True, exclude_none=True),
            headers=response_headers,
            status=status_code,
        )

    @http.route("/mcp/health", type="http", auth="public", methods=["GET", "POST"])
    def health_check(self):
        """Health check endpoint"""
        config = request.env["llm.mcp.server.config"].get_active_config()
        health_data = config.get_health_status_data()

        return http.Response(
            json.dumps(health_data, indent=2),
            headers={"Content-Type": "application/json"},
            status=HTTPStatus.OK,
        )

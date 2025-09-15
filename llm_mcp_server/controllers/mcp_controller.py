"""
MCP Server Controller for Odoo

Ultra-thin HTTP controller that routes requests to appropriate Odoo models 
following proper separation of concerns.
"""

import json
import logging
import time
from http import HTTPStatus
from typing import Optional

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


class MCPInitializeResponse(BaseModel):
    """Wrapper for MCP initialize method response"""
    result: InitializeResult
    session_id: Optional[str] = None


def require_bearer_auth(handler_func):
    """Decorator that applies MCP-compatible bearer authentication"""
    def wrapper(self, params, request_id):
            # Clean up the public uid and use built-in _auth_method_bearer
            request.update_env(user=False)
            request.env['ir.http']._auth_method_bearer()
            _logger.info("Bearer authentication succeeded %s", request.env.user)
            
            # Authentication succeeded - proceed with handler
            return handler_func(self, params, request_id)
            
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

    @http.route('/mcp', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def mcp_endpoint(self):
        """MCP endpoint for JSON-RPC methods"""
        request_id = None
        
        # Log incoming request details
        _logger.info("=== MCP REQUEST START ===")
        _logger.info(f"Method: {request.httprequest.method}")
        _logger.info(f"Headers: {dict(request.httprequest.headers)}")
        raw_body = request.httprequest.get_data(as_text=True)
        _logger.info(f"Body: {raw_body}")
        _logger.info("=== MCP REQUEST END ===")
        
        # Parse session ID once
        session_id = request.httprequest.headers.get('mcp-session-id')
        
        try:
            # Parse full JSON-RPC request - controller handles all protocol details
            request_data = self._parse_mcp_request()
            method = request_data['method']
            request_id = request_data.get('id')
            params = request_data.get('params', {})
            
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
            return self._build_rpc_success_response(request_id, result, response_session_id)
        
        except MCPError as e:
            # Handle all MCP-specific errors with their proper error codes
            return self._build_rpc_error_response(request_id, e.message, e.code)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception("Unexpected error in MCP endpoint")
            return self._build_rpc_error_response(request_id, f"Internal server error: {str(e)}", -32603)

    @http.route('/mcp', type='http', auth='bearer', methods=['DELETE'], csrf=False)
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
        
        if 'method' not in data:
            raise MCPInvalidRequestError("Missing 'method' in JSON-RPC request")
        
        # Validate basic JSON-RPC 2.0 structure
        if data.get('jsonrpc') != '2.0':
            raise MCPInvalidRequestError("Invalid JSON-RPC version, must be '2.0'")
        
        return data
    
    def _get_session(self, session_id):
        return request.env['llm.mcp.session'].get_session(
            session_id
        )

    def _validate_session_requirements(self, method_name, session_id):
        """Validate session requirements based on server mode and method"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        
        # For stateless mode, no session validation needed
        if config.mode == 'stateless':
            return None
        
        # For stateful mode, check session requirements
        if method_name not in ['initialize', 'ping']:
            if not session_id:
                return http.Response(
                    json.dumps({"error": "Missing mcp-session-id header"}),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )
            
            session = request.env['llm.mcp.session'].get_session(session_id)
            if not session:
                return http.Response(
                    json.dumps({"error": "Session not found"}),
                    headers={'Content-Type': 'application/json'}, 
                    status=404
                )
            
            # Check if method is allowed in current session state
            if not session.is_method_allowed(method_name):
                return http.Response(
                    json.dumps({
                        "error": "Bad Request",
                        "message": f"Method '{method_name}' not allowed in state '{session.state}'"
                    }),
                    headers={'Content-Type': 'application/json'},
                    status=400
                )
            
            # Update session activity
            session.update_activity()
        
        return None  # No error
    
    def _handle_delete_session(self):
        """Handle DELETE request for session termination"""
        session_id = request.httprequest.headers.get('mcp-session-id')
        
        if not session_id:
            return http.Response(
                'Missing mcp-session-id header',
                status=HTTPStatus.BAD_REQUEST  # Bad Request
            )
        
        # Find session using the model's get_session method
        session = request.env['llm.mcp.session'].get_session(session_id)
        
        if not session:
            return http.Response(
                'Session not found',
                status=HTTPStatus.NOT_FOUND  # Not Found
            )
        
        session.terminate()
        return http.Response('', status=HTTPStatus.NO_CONTENT)  # No Content
    
    # MCP Method Handlers
    def _mcp_initialize(self, params, request_id, session_id):
        """Handle initialize method"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        
        # Get server response (same for both modes)
        result = config.handle_initialize_request(client_info=params.get('clientInfo'))
        # For stateful mode, create new session
        if config.mode == 'stateful':
            session = request.env['llm.mcp.session'].create_new_session()
            
            # Store client information in session
            if params.get('clientInfo'):
                session.client_info = params['clientInfo']
            if params.get('capabilities'):
                session.client_capabilities = params['capabilities']
            if params.get('protocolVersion'):
                session.protocol_version = params['protocolVersion']
            
            # Transition to initializing state
            session.transition_to('initializing')
            
            # Return wrapped response with session_id
            return MCPInitializeResponse(result=result, session_id=session.session_id)
        
        # For stateless mode, return wrapped response without session_id
        return MCPInitializeResponse(result=result)
    
    def _mcp_notifications_initialized(self, params, request_id, session_id):
        """Handle notifications/initialized method"""
        # Get session and transition to initialized state
        if session_id:
            session = request.env['llm.mcp.session'].get_session(session_id)
            
            if session and session.state == 'initializing':
                session.transition_to('initialized')
        
        _logger.info("Client initialization complete")
        return http.Response(
            '',
            headers={
                "Content-Type": "application/json"
            },
            status=HTTPStatus.ACCEPTED
        )
    
    def _mcp_ping(self, params, request_id, session_id):
        """Handle ping method"""
        return {}
    
    def _mcp_tools_list(self, params, request_id, session_id):
        """Handle tools/list method"""
        return request.env['llm.tool'].get_mcp_tools_list(params=params)
    
    @require_bearer_auth
    def _mcp_tools_call(self, params, request_id, session_id):
        """Handle tools/call method"""
        return request.env['llm.tool'].execute_mcp_tool(params=params)

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

    def _build_rpc_success_response(self, request_id, result, session_id=None):
        """Build JSON-RPC 2.0 success response using MCP types
        
        Args:
            request_id: The JSON-RPC request ID
            result: MCP pydantic result object (InitializeResult, ListToolsResult, CallToolResult, etc.)
            session_id: Optional session ID for Mcp-Session-Id header
        """
        # Convert pydantic result object to dict for JSON-RPC response
        if hasattr(result, 'model_dump'):
            result_data = result.model_dump(exclude_none=True)
        else:
            result_data = result or {}
            
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=request_id if request_id is not None else int(time.time() * 1000),
            result=result_data
        )
        
        response_json = response.model_dump_json()
        response_headers = {'Content-Type': 'application/json'}
        
        # Add session ID header if present
        if session_id:
            response_headers['Mcp-Session-Id'] = session_id
        
        # Log outgoing response details
        _logger.info("=== MCP RESPONSE START ===")
        _logger.info(f"Status: {HTTPStatus.OK}")
        _logger.info(f"Headers: {response_headers}")
        _logger.info(f"Body: {response_json}")
        _logger.info("=== MCP RESPONSE END ===")
        
        return http.Response(
            response_json,
            headers=response_headers,
            status=HTTPStatus.OK  # JSON-RPC always uses 200
        )
    
    def _build_rpc_error_response(self, request_id, error, error_code):
        """Build JSON-RPC 2.0 error response using MCP types"""
        error_data = ErrorData(
            code=error_code,
            message=str(error)
        )
        
        response = JSONRPCError(
            jsonrpc="2.0",
            id=request_id if request_id is not None else int(time.time() * 1000),
            error=error_data
        )
        
        return http.Response(
            response.model_dump_json(),
            headers={'Content-Type': 'application/json'},
            status=HTTPStatus.OK  # JSON-RPC always uses 200, error is in response body
        )

    @http.route('/mcp/health', type='http', auth='public', methods=['GET', 'POST'])
    def health_check(self):
        """Health check endpoint"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        health_data = config.get_health_status_data()
        
        return http.Response(
            json.dumps(health_data, indent=2),
            headers={'Content-Type': 'application/json'},
            status=HTTPStatus.OK
        )
    
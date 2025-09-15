"""
MCP Server Controller for Odoo

Ultra-thin HTTP controller that routes requests to appropriate Odoo models 
following proper separation of concerns.
"""

import json
import logging
import time
from http import HTTPStatus

from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    ErrorData,
    JSONRPCError,
    JSONRPCResponse,
)

from odoo import http
from odoo.http import request


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

_logger = logging.getLogger(__name__)




class MCPController(http.Controller):
    """
    Ultra-thin MCP Server Controller following Odoo best practices.

    This controller delegates all business logic to Odoo models:
    - Config model handles initialize and server configuration
    - Tool model handles tools/list and tools/call
    - Authentication is handled by custom _auth_method_mcp_bearer
    """

    @http.route('/mcp', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False)
    def mcp_endpoint(self):
        """Single MCP endpoint with method-based conditional authentication"""
        request_id = None
        
        # Log incoming request details
        _logger.info("=== MCP REQUEST START ===")
        _logger.info(f"Method: {request.httprequest.method}")
        _logger.info(f"Headers: {dict(request.httprequest.headers)}")
        raw_body = request.httprequest.get_data(as_text=True)
        _logger.info(f"Body: {raw_body}")
        _logger.info("=== MCP REQUEST END ===")
        
        try:
            # Parse full JSON-RPC request - controller handles all protocol details
            request_data = self._parse_mcp_request()
            method = request_data['method']
            request_id = request_data.get('id')
            params = request_data.get('params', {})
            
            # Dispatch to appropriate handler
            result = self._dispatch(method, params, request_id)
            
            # Handle special case for notifications that return HTTP Response directly
            if isinstance(result, http.Response):
                return result
            
            # For all other methods, build JSON-RPC success response
            return self._build_rpc_success_response(request_id, result)
        
        except MCPError as e:
            # Handle all MCP-specific errors with their proper error codes
            return self._build_rpc_error_response(request_id, e.message, e.code)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception("Unexpected error in MCP endpoint")
            return self._build_rpc_error_response(request_id, f"Internal server error: {str(e)}", -32603)
    
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
    
    # MCP Method Handlers
    def _handle_initialize(self, params, request_id):
        """Handle initialize method"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        client_info = params.get('clientInfo')
        return config.handle_initialize_request(client_info=client_info)
    
    def _handle_notifications_initialized(self, params, request_id):
        """Handle notifications/initialized method"""
        _logger.info("Client initialization complete")
        return http.Response(
            '',
            headers={
                "Content-Type": "application/json"
            },
            status=HTTPStatus.ACCEPTED
        )
    
    def _handle_ping(self, params, request_id):
        """Handle ping method"""
        return {}
    
    def _handle_tools_list(self, params, request_id):
        """Handle tools/list method"""
        return request.env['llm.tool'].get_mcp_tools_list(params=params)
    
    def _handle_tools_call(self, params, request_id):
        """Handle tools/call method"""
        # Apply authentication for tools/call
        request.env['ir.http']._auth_method_mcp_bearer()
        return request.env['llm.tool'].execute_mcp_tool(params=params)

    def _dispatch(self, method_name, params, request_id):
        """Dispatch MCP method to appropriate handler"""
        # Transform method name to handler name
        handler_name = f"_handle_{method_name.replace('/', '_').replace('-', '_')}"
        
        # Get handler method
        handler = getattr(self, handler_name, None)
        if not handler:
            raise MCPMethodNotFoundError(method_name)
        
        # Call handler
        return handler(params, request_id)

    def _build_rpc_success_response(self, request_id, result):
        """Build JSON-RPC 2.0 success response using MCP types
        
        Args:
            request_id: The JSON-RPC request ID
            result: MCP pydantic result object (InitializeResult, ListToolsResult, CallToolResult, etc.)
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

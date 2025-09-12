"""
MCP Server Controller for Odoo

Ultra-thin HTTP controller that routes requests to appropriate Odoo models 
following proper separation of concerns.
"""

import json
import logging
import time

from mcp.types import ErrorData, JSONRPCError, JSONRPCResponse

from odoo import http
from odoo.http import request

from ..mcp_exceptions import (
    MCPError,
    MCPInvalidRequestError,
    MCPMethodNotFoundError,
    MCPParseError,
)

_logger = logging.getLogger(__name__)


class MCPController(http.Controller):
    """
    Ultra-thin MCP Server Controller following Odoo best practices.

    This controller delegates all business logic to Odoo models:
    - Config model handles initialize and server configuration
    - Tool model handles tools/list and tools/call
    - Authentication is handled by custom _auth_method_mcp_bearer
    """

    @http.route('/mcp', type='http', auth='public', methods=['POST'], csrf=False)
    def mcp_endpoint(self):
        """Single MCP endpoint with method-based conditional authentication"""
        request_id = None
        
        try:
            # Parse full JSON-RPC request - controller handles all protocol details
            request_data = self._parse_mcp_request()
            method = request_data['method']
            request_id = request_data.get('id')
            params = request_data.get('params', {})
            
            # Apply authentication only for tools/call (MCP protocol requirement)
            if method == 'tools/call':
                # Use our custom MCP-compatible bearer authentication
                request.env['ir.http']._auth_method_mcp_bearer()
            
            # Route to appropriate model based on method
            if method == 'initialize':
                config = request.env['llm.mcp.server.config'].get_active_config()
                client_info = params.get('clientInfo')
                result = config.handle_initialize_request(client_info=client_info)
                return self._build_success_response(request_id, result)
            elif method == 'tools/list':
                result = request.env['llm.tool'].handle_mcp_tools_list(params=params)
                return self._build_success_response(request_id, result)
            elif method == 'tools/call':
                result = request.env['llm.tool'].handle_mcp_tools_call(params=params)
                return self._build_success_response(request_id, result)
            else:
                raise MCPMethodNotFoundError(method)
        
        except MCPError as e:
            # Handle all MCP-specific errors with their proper error codes
            return self._build_error_response(request_id, e.message, e.code)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception("Unexpected error in MCP endpoint")
            return self._build_error_response(request_id, f"Internal server error: {str(e)}", -32603)
    
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
    
    def _build_success_response(self, request_id, result):
        """Build JSON-RPC 2.0 success response using MCP types"""
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=request_id or int(time.time() * 1000),
            result=result or {}
        )
        
        return http.Response(
            response.model_dump_json(),
            headers={'Content-Type': 'application/json'},
            status=200  # JSON-RPC always uses 200
        )
    
    def _build_error_response(self, request_id, error, error_code):
        """Build JSON-RPC 2.0 error response using MCP types"""
        error_data = ErrorData(
            code=error_code,
            message=str(error)
        )
        
        response = JSONRPCError(
            jsonrpc="2.0",
            id=request_id or int(time.time() * 1000),
            error=error_data
        )
        
        return http.Response(
            response.model_dump_json(),
            headers={'Content-Type': 'application/json'},
            status=200  # JSON-RPC always uses 200, error is in response body
        )

    @http.route('/mcp/health', type='http', auth='public', methods=['GET', 'POST'])
    def health_check(self):
        """Health check endpoint"""
        config = request.env['llm.mcp.server.config'].get_active_config()
        health_data = config.get_health_status_data()
        
        return http.Response(
            json.dumps(health_data, indent=2),
            headers={'Content-Type': 'application/json'},
            status=200
        )

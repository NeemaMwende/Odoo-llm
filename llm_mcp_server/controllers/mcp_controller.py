"""
MCP Server Controller for Odoo

Thin HTTP controller that orchestrates MCP components following proper separation of concerns.
"""

import logging

from mcp.types import INTERNAL_ERROR, METHOD_NOT_FOUND

from odoo import http
from odoo.http import request

from ..mcp_request_handler import MCPRequestHandler
from ..mcp_session_manager import MCPSessionManager
from ..mcp_transport import MCPTransport
from ..mcp_validator import MCPValidator

_logger = logging.getLogger(__name__)


class MCPServerController(http.Controller):
    """
    Thin MCP Server Controller that orchestrates components.

    This controller follows Odoo best practices by being thin and delegating
    business logic to specialized service classes, following MCP SDK patterns.

    Components:
    - MCPSessionManager: Session lifecycle and configuration
    - MCPValidator: Protocol validation and authentication  
    - MCPRequestHandler: JSON-RPC request processing
    - MCPTransport: HTTP/SSE transport handling
    """

    def _get_components(self):
        """Get initialized MCP components"""
        session_manager = MCPSessionManager()
        validator = MCPValidator()
        request_handler = MCPRequestHandler(session_manager, validator)
        transport = MCPTransport(session_manager, validator, request_handler)
        
        return transport

    @http.route("/mcp", type="http", auth="public", methods=["GET", "POST", "DELETE"], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint - routes to transport layer.

        This is the only HTTP routing logic. All business logic is delegated
        to the transport layer following proper separation of concerns.
        """
        method = request.httprequest.method
        headers = dict(request.httprequest.headers)
        body = request.httprequest.get_data(as_text=True) if method == "POST" else ""
        
        _logger.info("=== MCP REQUEST START ===")
        _logger.info(f"Method: {method}")
        _logger.info(f"Headers: {headers}")
        _logger.info(f"Body: {body[:500]}...")  # First 500 chars to avoid huge logs
        
        transport = self._get_components()
        
        try:
            if method == "POST":
                result = transport.handle_post_request()
            elif method == "GET":
                result = transport.handle_get_request()
            elif method == "DELETE":
                result = transport.handle_delete_request()
            else:
                result = transport.http_error_response(None, METHOD_NOT_FOUND, f"Method {method} not supported")
            
            _logger.info("=== MCP RESPONSE ===")
            if hasattr(result, 'data'):
                response_data = result.data[:500] if isinstance(result.data, str) else str(result.data)[:500]
                _logger.info(f"Response data: {response_data}...")
            if hasattr(result, 'status_code'):
                _logger.info(f"Status code: {result.status_code}")
            _logger.info("=== MCP REQUEST END ===")
            
            return result
                
        except Exception as e:
            _logger.exception(f"Unhandled error in MCP server: {e}")
            error_response = transport.http_error_response(None, INTERNAL_ERROR, f"Internal error: {str(e)}")
            _logger.info("=== MCP ERROR RESPONSE ===")
            _logger.info(f"Error response: {error_response}")
            _logger.info("=== MCP REQUEST END ===")
            return error_response

    @http.route("/mcp/health", type="json", auth="public", methods=["GET", "POST"], csrf=False)
    def health_check(self, **_params):
        """
        Health check endpoint for MCP server.
        
        Uses public authentication to respect Odoo's access control system
        while still allowing basic health checks.
        """
        try:
            # Count available tools (respects current user's access rights)
            tools_count = request.env["llm.tool"].search_count([("active", "=", True)])

            # Get configuration from database (respects current user's access rights)
            config_model = request.env["llm.mcp.server.config"]
            config = config_model.get_active_config()

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
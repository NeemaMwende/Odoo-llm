"""
MCP Request Handler

Handles JSON-RPC 2.0 request processing and tool execution.
"""

import json
import logging
from typing import Any, Optional

from mcp.types import (
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    ListToolsResult,
)
from pydantic import ValidationError

from odoo.http import request

from .mcp_exceptions import (
    MCPInvalidParamsError,
    MCPInvalidRequestError,
    MCPMethodNotFoundError,
    MCPParseError,
    MCPToolAccessDeniedError,
    MCPToolNotFoundError,
)

_logger = logging.getLogger(__name__)


class MCPRequestHandler:
    """
    Handles MCP JSON-RPC 2.0 request processing.
    
    Separates request handling logic from HTTP transport concerns.
    """

    def __init__(self, session_manager, validator):
        self.session_manager = session_manager
        self.validator = validator

    def parse_request(self) -> JSONRPCMessage:
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
            raise MCPParseError() from e
        except ValidationError as e:
            _logger.error(f"Invalid JSON-RPC message structure: {e}")
            raise MCPInvalidRequestError(f"Invalid JSON-RPC format: {e}") from e

    def route_request(self, message: JSONRPCMessage):
        """Route request to appropriate handler"""
        request_obj = message.root
        
        # Handle notifications vs requests
        if isinstance(request_obj, JSONRPCNotification):
            return self.handle_notification(request_obj)
        elif isinstance(request_obj, JSONRPCRequest):
            return self.handle_request(request_obj)
        else:
            raise MCPInvalidRequestError("Unknown JSON-RPC message type")

    def handle_notification(self, notification: JSONRPCNotification):
        """
        Handle JSON-RPC notifications.
        
        According to MCP specification, notifications should return 202 Accepted with no body.
        """
        if notification.method == "notifications/initialized":
            _logger.info("MCP client initialization complete")
        else:
            _logger.warning(f"Unknown notification method: {notification.method}")
        
        # MCP specification: notifications return 202 Accepted with no body
        from odoo import http
        return http.Response("", status=202, headers={})

    def handle_request(self, request_obj: JSONRPCRequest):
        """Handle JSON-RPC requests"""
        method = request_obj.method
        request_id = request_obj.id
        request_params = request_obj.params or {}
        
        # Method is guaranteed to exist by MCP SDK validation
        if not method:
            raise MCPInvalidRequestError("Missing required 'method' field")
        
        # Check if authentication is required for this method
        if self.validator.is_authentication_required(method):
            self.validator.authenticate_api_key_or_error()
        
        # Route to specific handlers
        if method == "initialize":
            return self.handle_initialize(request_id, request_params)
        elif method == "tools/list":
            return self.handle_tools_list(request_id, request_params)
        elif method == "tools/call":
            return self.handle_tools_call(request_id, request_params)
        else:
            raise MCPMethodNotFoundError(method)

    def handle_initialize(self, request_id: Optional[Any], params: dict[str, Any]):
        """Handle MCP initialize request"""
        # Get session ID
        session_id = self.session_manager.get_session_id()
        
        # Store client information if provided
        client_info = params.get("clientInfo")
        if client_info:
            self.session_manager.log_client_connection(client_info)
        
        # Get configuration from database
        config = self.session_manager.get_server_config()

        # Build capabilities
        from mcp.types import ServerCapabilities, ToolsCapability
        capabilities = ServerCapabilities(
            tools=ToolsCapability(listChanged=False)
        ).model_dump(exclude_none=True)

        result = {
            "protocolVersion": config.protocol_version,
            "capabilities": capabilities,
            "serverInfo": {"name": config.name, "version": config.version},
            # Return session ID for MCP protocol compliance
            "sessionId": session_id
        }

        return result

    def handle_tools_list(self, request_id: Optional[Any], _params: dict[str, Any]):
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
        return result.model_dump(exclude_none=True)

    def handle_tools_call(self, request_id: Optional[Any], params: dict[str, Any]):
        """Handle tools/call request (authentication already handled)"""
        tool_name, arguments = self.extract_tool_params(params)
        tool = self.get_authorized_tool(tool_name, request.env.user)
        result = self.execute_tool_safely(tool, arguments, request.env.user)
        return result

    def extract_tool_params(self, params: dict):
        """Extract and validate tool parameters"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise MCPInvalidParamsError("Missing tool name")
        
        return tool_name, arguments

    def get_authorized_tool(self, tool_name: str, user):
        """Get tool and verify user access"""
        # Find the tool with user context (not sudo!)
        tool = request.env["llm.tool"].search(
            [("name", "=", tool_name), ("active", "=", True)], limit=1
        )
        
        if not tool:
            raise MCPToolNotFoundError(tool_name)
        
        # Check if user has access to this tool
        try:
            tool.check_access('read')
            return tool
        except Exception as e:
            _logger.warning(f"User {user.login} denied access to tool {tool_name}: {e}")
            raise MCPToolAccessDeniedError(tool_name) from e

    def execute_tool_safely(self, tool, arguments: dict, user) -> dict:
        """Execute tool and format result for MCP"""
        try:
            result = tool.execute(arguments)
            content_text = self.format_tool_result(result)
            
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

    def format_tool_result(self, result) -> str:
        """Format tool execution result as string"""
        return (
            json.dumps(result, indent=2)
            if isinstance(result, dict)
            else str(result)
        )
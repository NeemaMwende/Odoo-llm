import json
import logging
import time
from typing import Any, Optional

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


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
        which OpenAI requires for array types.

        This uses the same logic as the OpenAI provider in llm_openai.
        """
        if not isinstance(schema_node, dict):
            return

        # Fix array items that don't have a type
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

    @http.route("/mcp", type="http", auth="none", methods=["POST"], csrf=False)
    def mcp_server(self):
        """
        Main MCP server endpoint handling JSON-RPC 2.0 requests

        This endpoint routes MCP protocol messages to appropriate handlers.
        """
        try:
            # Read the raw request body
            raw_body = request.httprequest.get_data(as_text=True)
            _logger.info(f"Raw MCP Request received: {raw_body}")

            # Parse JSON from raw body
            if not raw_body.strip():
                params = {}
            else:
                try:
                    params = json.loads(raw_body)
                except json.JSONDecodeError as e:
                    _logger.error(f"Invalid JSON in request: {e}")
                    return self._http_error_response(None, -32700, "Parse error")

            _logger.info(f"Parsed MCP Request: {json.dumps(params)}")

            # Extract JSON-RPC fields
            jsonrpc = params.get("jsonrpc", "2.0")
            method = params.get("method")
            request_id = params.get("id")
            request_params = params.get("params", {})

            # Validate JSON-RPC version
            if jsonrpc != "2.0":
                return self._http_error_response(
                    request_id, -32600, f"Invalid JSON-RPC version: {jsonrpc}"
                )

            # Handle missing method (likely an initialization probe)
            if not method or method == "None":
                # Default to initialize if no method specified
                _logger.info("No method specified, defaulting to initialize")
                return self._http_handle_initialize(request_id, request_params)

            # Route to appropriate handler based on method
            if method == "initialize":
                return self._http_handle_initialize(request_id, request_params)
            elif method == "tools/list":
                return self._http_handle_tools_list(request_id, request_params)
            elif method == "tools/call":
                return self._http_handle_tools_call(request_id, request_params)
            elif method == "notifications/initialized":
                # Client notification that initialization is complete
                _logger.info("MCP client initialization complete")
                return http.Response("", status=204)  # No content for notifications
            else:
                return self._http_error_response(
                    request_id, -32601, f"Method not found: {method}"
                )

        except Exception as e:
            _logger.exception(f"Error in MCP server: {e}")
            return self._http_error_response(None, -32603, f"Internal error: {str(e)}")

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
            headers={"Content-Type": "application/json"},
            status=200,
        )

    def _http_handle_initialize(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle MCP initialize request"""
        try:
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

        except Exception as e:
            _logger.exception(f"Error in initialize: {e}")
            return self._http_error_response(request_id, -32603, str(e))

    def _http_handle_tools_list(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/list request"""
        try:
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

        except Exception as e:
            _logger.exception(f"Error listing tools: {e}")
            return self._http_error_response(request_id, -32603, str(e))

    def _http_handle_tools_call(
        self, request_id: Optional[Any], params: dict[str, Any]
    ):
        """Handle tools/call request"""
        try:
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            _logger.info(f"MCP tools/call request for tool: {tool_name}")

            if not tool_name:
                return self._http_error_response(
                    request_id, -32602, "Missing tool name"
                )

            # Find the tool
            tools_model = request.env["llm.tool"].sudo()
            tool = tools_model.search(
                [("name", "=", tool_name), ("active", "=", True)], limit=1
            )

            if not tool:
                return self._http_error_response(
                    request_id, -32602, f"Tool not found: {tool_name}"
                )

            # Execute the tool
            try:
                result = tool.execute(arguments)

                # Format result for MCP
                content_text = (
                    json.dumps(result, indent=2)
                    if isinstance(result, dict)
                    else str(result)
                )

                mcp_result = {
                    "content": [{"type": "text", "text": content_text}],
                    "isError": False,
                }

                _logger.info(f"Tool {tool_name} executed successfully")
                return self._json_rpc_http_response(request_id, result=mcp_result)

            except Exception as e:
                _logger.exception(f"Error executing tool {tool_name}: {e}")

                # Return tool error in result (not as JSON-RPC error)
                mcp_result = {
                    "content": [
                        {"type": "text", "text": f"Tool execution failed: {str(e)}"}
                    ],
                    "isError": True,
                }
                return self._json_rpc_http_response(request_id, result=mcp_result)

        except Exception as e:
            _logger.exception(f"Error in tools/call: {e}")
            return self._http_error_response(request_id, -32603, str(e))

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

"""
MCP Protocol Validator

Handles all MCP protocol validation including headers, content types, and authentication.
"""

import logging
import re
from typing import Optional

from mcp.server.streamable_http import MCP_PROTOCOL_VERSION_HEADER

from odoo.http import request

from .mcp_exceptions import MCPAuthenticationError

_logger = logging.getLogger(__name__)


class MCPValidator:
    """
    Handles MCP protocol validation per specification.

    Validates headers, content types, authentication, and protocol compliance.
    """

    # Methods that require API key authentication
    AUTHENTICATED_METHODS = {
        "tools/call",
        # Add future authenticated methods here
    }

    def is_authentication_required(self, method: str) -> bool:
        """Determine if API key authentication is required for this method"""
        return method in self.AUTHENTICATED_METHODS

    def validate_accept_headers(self, method: str) -> Optional[str]:
        """
        Validate Accept headers per MCP specification.

        Returns error message if invalid, None if valid.
        """
        accept_header = request.httprequest.headers.get("accept", "")

        if method == "POST":
            # POST MUST accept BOTH application/json AND text/event-stream
            required_types = ["application/json", "text/event-stream"]

            # Check if accept header contains both required types or is wildcard
            if accept_header == "*/*" or "application/*" in accept_header:
                return None  # Wildcard accepts everything

            missing_types = []
            for required_type in required_types:
                if required_type not in accept_header:
                    missing_types.append(required_type)

            if missing_types:
                return (
                    f"POST requests must accept both application/json and text/event-stream. "
                    f"Missing: {', '.join(missing_types)}"
                )

        elif method == "GET":
            # GET MUST accept text/event-stream for SSE
            if "text/event-stream" not in accept_header and accept_header not in [
                "*/*",
                "text/*",
            ]:
                return "GET requests must accept text/event-stream for SSE streaming"

        return None  # Valid headers

    def validate_content_type(self, method: str) -> Optional[str]:
        """
        Validate Content-Type headers per MCP specification.

        Returns error message if invalid, None if valid.
        """
        if method != "POST":
            return None  # Only validate POST content-type

        content_type = request.httprequest.headers.get("content-type", "")

        if not content_type.startswith("application/json"):
            return "POST requests must have Content-Type: application/json"

        return None  # Valid content-type

    def validate_protocol_version(self, server_config) -> Optional[str]:
        """
        Validate MCP protocol version header.

        Returns warning message if different, None if valid.
        """
        protocol_version = request.httprequest.headers.get(
            MCP_PROTOCOL_VERSION_HEADER, ""
        )

        if protocol_version and protocol_version != server_config.protocol_version:
            warning = (
                f"Client protocol version {protocol_version} differs from "
                f"server {server_config.protocol_version}"
            )
            _logger.warning(warning)
            # This is a warning, not an error - servers should be backwards compatible

        return None  # Protocol version validation is informational

    def extract_api_key(self) -> Optional[str]:
        """Extract API key from Authorization Bearer or X-API-KEY header"""
        # Check Authorization: Bearer <key>
        header = request.httprequest.headers.get("Authorization")
        if header:
            match = re.match(r"^Bearer\s+(.+)$", header, re.IGNORECASE)
            if match:
                return match.group(1)

        # Fallback to X-API-KEY header
        return request.httprequest.headers.get("X-API-KEY")

    def authenticate_api_key_or_error(self):
        """
        Validate API key and bind request to corresponding user.

        Raises ValueError on failure with descriptive message.
        """
        token = self.extract_api_key()
        if not token:
            raise MCPAuthenticationError(
                "Missing API key in Authorization or X-API-KEY header"
            )

        # Validate API key using Odoo's built-in system
        # We create keys with scope=None which matches any scope, so we can use 'rpc' for validation
        uid = request.env["res.users.apikeys"]._check_credentials(
            scope="rpc", key=token
        )
        if not uid:
            raise MCPAuthenticationError("Invalid API key")

        # Bind request environment to API key owner
        request.update_env(user=uid)
        # Success - no exception raised

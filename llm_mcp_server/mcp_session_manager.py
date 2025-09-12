"""
MCP Session Manager for Odoo

Handles session lifecycle and management following MCP SDK patterns.
"""

import logging
from typing import Optional

from odoo.http import request

from .event_store import InMemoryEventStore

_logger = logging.getLogger(__name__)


class MCPSessionManager:
    """
    Manages MCP sessions with optional event storage for resumability.

    This follows the MCP SDK pattern but integrates with Odoo's session system.
    """

    # Class-level event store (shared across all sessions)
    _event_store = None

    @classmethod
    def get_event_store(cls) -> InMemoryEventStore:
        """Get or create the shared event store instance"""
        if cls._event_store is None:
            cls._event_store = InMemoryEventStore(max_events_per_stream=100)
        return cls._event_store

    def get_session_id(self) -> str:
        """
        Get session ID from MCP header or Odoo session.

        This integrates MCP session management with Odoo's built-in sessions.
        """
        from mcp.server.streamable_http import MCP_SESSION_ID_HEADER

        # Check for explicit MCP session ID header first
        mcp_session_id = request.httprequest.headers.get(MCP_SESSION_ID_HEADER)
        if mcp_session_id:
            return mcp_session_id

        # Fallback to Odoo session ID (most common case)
        return request.session.sid

    def get_server_config(self):
        """Get the active MCP server configuration"""
        config_model = request.env["llm.mcp.server.config"].sudo()
        return config_model.get_active_config()

    def is_stateless_mode(self) -> bool:
        """Check if server is configured for stateless mode"""
        config = self.get_server_config()
        return config.stateless_mode

    def is_resumability_enabled(self) -> bool:
        """Check if resumability is enabled"""
        config = self.get_server_config()
        return config.enable_resumability

    def validate_session_id_format(self, session_id: str) -> bool:
        """Validate session ID format"""
        # Odoo generates proper session IDs, so this is mainly for external validation
        if not session_id or len(session_id) < 10:
            return False
        return True

    def log_client_connection(self, client_info: Optional[dict] = None):
        """Log MCP client connection information"""
        if client_info:
            _logger.info(
                f"MCP client connected: {client_info.get('name', 'Unknown')} "
                f"v{client_info.get('version', 'Unknown')}"
            )
        else:
            _logger.info("MCP client connected (no client info provided)")

    def log_session_deletion(self, session_id: str):
        """Log session deletion request"""
        _logger.info(f"Session {session_id} deletion requested")

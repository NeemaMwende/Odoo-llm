import json
import logging
import time

import odoo.http as odoo_http

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.service import security

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    # MCP Session metadata
    mcp_metadata = fields.Json(
        string='MCP Metadata',
        help='JSON metadata for storing MCP session IDs, agent info, etc.',
        default=dict
    )

    def ensure_mcp_session(self):
        """Ensure thread has an MCP session for external tool access"""
        
        # Check if we already have a session
        metadata = self.mcp_metadata or {}
        existing_session_id = metadata.get('mcp_session_id')
        
        if existing_session_id:
            try:
                # Verify session is still valid
                session = odoo_http.root.session_store.get(existing_session_id)
                if session and session.get('usage_type') == 'mcp' and session.get('uid') == self.env.user.id:
                    _logger.info(f"Using existing MCP session {existing_session_id} for thread {self.id}")
                    return existing_session_id
                else:
                    _logger.info(f"Existing session {existing_session_id} invalid, creating new one")
            except Exception as e:
                _logger.warning(f"Error validating existing session: {e}")

        # Create new MCP session
        mcp_session = odoo_http.root.session_store.new()
        
        # Configure session for MCP usage - only essential fields
        mcp_session.update({
            'db': self.env.cr.dbname,
            'uid': self.env.user.id,
            'login': self.env.user.login,
            'context': self.env.context.copy(),
            
            # MCP-specific metadata  
            'usage_type': 'mcp',
            'created_at': time.time(),
        })
        
        # Generate security token
        if mcp_session.uid:
            mcp_session.session_token = security.compute_session_token(mcp_session, self.env)
        
        # Save session
        odoo_http.root.session_store.save(mcp_session)
        
        # Store session ID in thread metadata
        metadata['mcp_session_id'] = mcp_session.sid
        self.mcp_metadata = metadata
        
        _logger.info(f"Created new MCP session {mcp_session.sid} for thread {self.id}")
        return mcp_session.sid

    def get_mcp_session_id(self):
        """Get the MCP session ID for this thread"""
        metadata = self.mcp_metadata or {}
        return metadata.get('mcp_session_id')

    def clear_mcp_session(self):
        """Clear the MCP session for this thread"""
        metadata = self.mcp_metadata or {}
        session_id = metadata.get('mcp_session_id')
        
        if session_id:
            try:
                # Delete session from Odoo's session store
                session = odoo_http.root.session_store.get(session_id)
                if session:
                    odoo_http.root.session_store.delete(session)
                    _logger.info(f"Deleted MCP session {session_id} for thread {self.id}")
            except Exception as e:
                _logger.warning(f"Error deleting MCP session {session_id}: {e}")
            
            # Remove from metadata
            metadata.pop('mcp_session_id', None)
            self.mcp_metadata = metadata
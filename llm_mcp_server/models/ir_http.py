"""
MCP-Compatible HTTP Authentication

Extends Odoo's ir.http model to provide MCP protocol compatible bearer token authentication.
Unlike Odoo's built-in _auth_method_bearer, this allows anonymous→authenticated transitions
required by MCP protocol where clients start anonymous and authenticate per method.
"""

import werkzeug.datastructures
import werkzeug.exceptions

from odoo import models
from odoo.exceptions import AccessDenied
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'
    
    @classmethod
    def authenticate_mcp_bearer_token(cls):
        """MCP-compatible bearer authentication utility method.
        
        Unlike Odoo's _auth_method_bearer, this allows anonymous→authenticated 
        transition required by MCP protocol where:
        1. Client starts with public user session
        2. Some methods (initialize, tools/list) remain anonymous
        3. Other methods (tools/call) require API key authentication
        4. API key user may differ from session user
        
        Returns:
            int: User ID of authenticated user
            
        Raises:
            werkzeug.exceptions.Unauthorized: If token is missing or invalid
            AccessDenied: If session conflicts with API key user (non-MCP case)
        """
        headers = request.httprequest.headers
        header = headers.get("Authorization")
        
        if not header or not header.lower().startswith("bearer "):
            raise werkzeug.exceptions.Unauthorized(
                "Missing bearer token",
                www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer')
            )
        
        token = header[7:]  # Remove "Bearer " prefix
        
        # Use Odoo's exact same API key validation logic
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
        if not uid:
            raise werkzeug.exceptions.Unauthorized(
                "Invalid apikey",
                www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer')
            )
        
        # MCP-specific: Allow transition from public user to authenticated user
        public_user_id = request.env.ref('base.public_user').id
        if request.env.uid in (public_user_id, None):
            # Anonymous or public user - safe to authenticate with API key
            request.update_env(user=uid)
        elif request.env.uid != uid:
            # Session already bound to different user - conflict
            raise AccessDenied("Session user does not match API key user")
        
        return uid
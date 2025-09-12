"""
MCP-Compatible HTTP Authentication

Extends Odoo's ir.http model to provide MCP protocol compatible bearer token authentication.
This adds _auth_method_mcp_bearer which is nearly identical to Odoo's _auth_method_bearer
but allows anonymous→authenticated transitions required by MCP protocol.
"""

import re

import werkzeug.datastructures
import werkzeug.exceptions

from odoo import models
from odoo.exceptions import AccessDenied
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'
    
    @classmethod
    def _auth_method_mcp_bearer(cls):
        """MCP-compatible bearer authentication method.
        
        This is nearly identical to Odoo's _auth_method_bearer but allows 
        anonymous→authenticated transitions required by MCP protocol.
        
        Key difference: Allows public user sessions to authenticate with API key,
        which MCP clients need when they start anonymous and authenticate per method.
        """
        headers = request.httprequest.headers

        def get_http_authorization_bearer_token():
            # werkzeug<2.3 doesn't expose `authorization.token` (for bearer authentication)
            # check header directly
            header = headers.get("Authorization")
            if header and (m := re.match(r"^bearer\s+(.+)$", header, re.IGNORECASE)):
                return m.group(1)
            return None

        def check_sec_headers():
            """Protection against CSRF attacks.
            Modern browsers automatically add Sec- headers that we can check to protect against CSRF.
            https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Sec-Fetch-User
            """
            return (
                headers.get("Sec-Fetch-Dest") == "document"
                and headers.get("Sec-Fetch-Mode") == "navigate"
                and headers.get("Sec-Fetch-Site") in ('none', 'same-origin')
                and headers.get("Sec-Fetch-User") == "?1"
            )

        if token := get_http_authorization_bearer_token():
            # 'rpc' scope does not really exist, we basically require a global key (scope NULL)
            uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)
            if not uid:
                raise werkzeug.exceptions.Unauthorized(
                    "Invalid apikey",
                    www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer'))
            
            # MCP-specific change: Allow public user to authenticate with API key
            public_user_ids = cls._get_public_users()
            if request.env.uid and request.env.uid not in public_user_ids and request.env.uid != uid:
                # Only raise error if session is bound to a non-public user different from API key user
                raise AccessDenied("Session user does not match the used apikey")
            
            request.update_env(user=uid)
        elif not request.env.uid:
            raise werkzeug.exceptions.Unauthorized(
                'User not authenticated, use the "Authorization" header',
                www_authenticate=werkzeug.datastructures.WWWAuthenticate('bearer'))
        elif not check_sec_headers():
            raise AccessDenied("Missing \"Authorization\" or Sec-headers for interactive usage")
        
        cls._auth_method_user()
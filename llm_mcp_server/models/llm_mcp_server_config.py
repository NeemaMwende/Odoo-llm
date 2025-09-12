from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LLMMCPServerConfig(models.Model):
    _name = "llm.mcp.server.config"
    _description = "MCP Server Configuration"
    _inherit = ["mail.thread"]

    name = fields.Char(
        string="Server Name",
        required=True,
        default="Odoo LLM MCP Server",
        tracking=True,
    )
    version = fields.Char(
        string="Server Version",
        required=True,
        default="1.0.0",
        tracking=True,
    )
    protocol_version = fields.Char(
        string="Protocol Version",
        required=True,
        default="2024-11-05",
        tracking=True,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
    )
    external_url = fields.Char(
        string="External URL",
        help="External URL that Letta can reach (e.g., http://host.docker.internal:8069 for Docker). "
        "Leave empty to auto-detect from web.base.url",
        tracking=True,
    )

    # MCP Server Mode Configuration
    mode = fields.Selection([
        ('stateless', 'Stateless Mode'),
        # ('stateful', 'Stateful Mode'),  # Future implementation
    ], default='stateless', required=True, tracking=True,
       help="Server operation mode")

    @api.constrains("active")
    def _check_single_active_record(self):
        """Ensure only one config record can be active at a time"""
        if self.active:
            other_active = self.search([("id", "!=", self.id), ("active", "=", True)])
            if other_active:
                raise ValidationError(
                    "Only one MCP Server configuration can be active at a time."
                )

    @api.model
    def get_active_config(self):
        """Get the active MCP server configuration"""
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            # Create default config if none exists
            config = self.create(
                {
                    "name": "Odoo LLM MCP Server",
                    "version": "1.0.0",
                    "protocol_version": "2024-11-05",
                    "active": True,
                }
            )
        return config

    def get_mcp_server_url(self):
        """Get the MCP server URL that external clients can reach"""
        if self.external_url:
            return f"{self.external_url.rstrip('/')}/mcp"
        else:
            base_url = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("web.base.url", "http://localhost:8069")
            )
            return f"{base_url}/mcp"
    
    def handle_initialize_request(self, client_info=None):
        """Handle MCP initialize request - return MCP InitializeResult"""
        from mcp.types import Implementation, InitializeResult
        
        server_info = Implementation(name=self.name, version=self.version)
        
        return InitializeResult(
            protocolVersion=self.protocol_version,
            capabilities=self._get_server_capabilities(),
            serverInfo=server_info
        )
    
    def _get_server_capabilities(self):
        """Get server capabilities based on configuration"""
        from mcp.types import ServerCapabilities, ToolsCapability
        
        capabilities = ServerCapabilities(
            tools=ToolsCapability(listChanged=False)
        )
        return capabilities
    
    def get_health_status_data(self):
        """Get health status data - return plain dict"""
        return {
            "status": "healthy",
            "server": self.name,
            "version": self.version
        }
    

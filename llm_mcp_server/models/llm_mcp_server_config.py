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
    
    @api.constrains('active')
    def _check_single_active_record(self):
        """Ensure only one config record can be active at a time"""
        if self.active:
            other_active = self.search([('id', '!=', self.id), ('active', '=', True)])
            if other_active:
                raise ValidationError("Only one MCP Server configuration can be active at a time.")
    
    @api.model
    def get_active_config(self):
        """Get the active MCP server configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            # Create default config if none exists
            config = self.create({
                'name': 'Odoo LLM MCP Server',
                'version': '1.0.0', 
                'protocol_version': '2024-11-05',
                'active': True,
            })
        return config
import json

from odoo import _, api, fields, models
from odoo.addons.base.models.res_users import check_identity


class APIKeyDescriptionMCP(models.TransientModel):
    """Extend API Key Description wizard to support MCP key generation."""

    _inherit = "res.users.apikeys.description"

    @check_identity
    def make_key(self):
        """Override to show MCP configs when is_mcp_key context is set."""
        if not self.env.context.get("is_mcp_key"):
            return super().make_key()

        # Same key generation logic as parent
        self.check_access_make_key()

        description = self.sudo()
        k = self.env["res.users.apikeys"]._generate(
            None, description.name, self.expiration_date
        )
        description.unlink()

        # Get MCP URL and generate configs
        try:
            config = self.env["llm.mcp.server.config"].get_active_config()
            mcp_url = config.get_mcp_server_url()
        except Exception:
            base_url = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("web.base.url", "http://localhost:8069")
            )
            mcp_url = f"{base_url}/mcp"

        configs = self.env["llm.mcp.key.show"]._generate_configs(k, mcp_url)

        # Return MCP-specific show view with configs
        return {
            "type": "ir.actions.act_window",
            "res_model": "llm.mcp.key.show",
            "name": _("MCP Key Ready"),
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_key": k,
                "default_mcp_url": mcp_url,
                "default_config_claude_desktop": configs["claude_desktop"],
                "default_config_claude_code": configs["claude_code"],
                "default_config_cursor": configs["cursor"],
                "default_config_codex": configs["codex"],
            },
        }


class LlmMcpKeyShow(models.AbstractModel):
    """Show MCP Key with ready-to-use configuration snippets."""

    _name = "llm.mcp.key.show"
    _description = "Show MCP Key with Configs"

    # Required for onchange that returns the key value
    id = fields.Id()
    key = fields.Char(readonly=True)
    mcp_url = fields.Char(readonly=True, string="MCP URL")

    # Config snippets for different clients (populated via context defaults)
    config_claude_desktop = fields.Text(readonly=True, string="Claude Desktop")
    config_claude_code = fields.Text(readonly=True, string="Claude Code")
    config_cursor = fields.Text(readonly=True, string="Cursor")
    config_codex = fields.Text(readonly=True, string="Codex (OpenAI)")

    @api.model
    def _generate_configs(self, key, mcp_url):
        """Generate configuration snippets for each MCP client.

        Args:
            key: The generated API key
            mcp_url: The MCP server URL

        Returns:
            dict with config strings for each client
        """
        # Claude Desktop - JSON config with stdio type and env
        claude_desktop_config = {
            "mcpServers": {
                "odoo-llm-mcp-server": {
                    "type": "stdio",
                    "command": "npx",
                    "args": [
                        "-y",
                        "mcp-remote",
                        mcp_url,
                        "--header",
                        f"Authorization: Bearer {key}",
                    ],
                    "env": {"MCP_TRANSPORT": "streamable-http"},
                }
            }
        }

        # Claude Code - CLI command
        claude_code_cmd = f"""claude mcp add-json odoo-llm-mcp-server '{{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "mcp-remote", "{mcp_url}",
           "--header", "Authorization: Bearer {key}"],
  "env": {{"MCP_TRANSPORT": "streamable-http"}}
}}'"""

        # Cursor - similar to Claude Desktop
        cursor_config = {
            "mcpServers": {
                "odoo-llm-mcp-server": {
                    "type": "stdio",
                    "command": "npx",
                    "args": [
                        "-y",
                        "mcp-remote",
                        mcp_url,
                        "--header",
                        f"Authorization: Bearer {key}",
                    ],
                    "env": {"MCP_TRANSPORT": "streamable-http"},
                }
            }
        }

        # Codex CLI - TOML format
        codex_config = f"""experimental_use_rmcp_client = true

[mcp_servers.odoo-llm-mcp-server]
url = "{mcp_url}"
http_headers.Authorization = "Bearer {key}"
"""

        return {
            "claude_desktop": json.dumps(claude_desktop_config, indent=2),
            "claude_code": claude_code_cmd,
            "cursor": json.dumps(cursor_config, indent=2),
            "codex": codex_config,
        }

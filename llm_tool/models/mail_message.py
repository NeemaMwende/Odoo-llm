import json
import logging

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"

    # Add computed field for display purposes
    display_body = fields.Html(
        string="Display Body",
        compute="_compute_display_body",
        help="Human-readable version of the message body, parsed from JSON for tool messages"
    )

    @api.depends('body', 'llm_role')
    def _compute_display_body(self):
        """Compute display body that shows human-readable content for tool messages."""
        for record in self:
            if record.llm_role == 'tool':
                try:
                    tool_data = json.loads(record.body)
                    tool_name = tool_data.get('tool_name', 'Unknown Tool')
                    status = tool_data.get('status', 'unknown')
                    
                    if status == 'executing':
                        record.display_body = f"Executing: {tool_name}..."
                    elif status == 'completed':
                        record.display_body = f"Completed: {tool_name}"
                    elif status == 'error':
                        record.display_body = f"Error in: {tool_name}"
                    else:
                        record.display_body = f"Tool: {tool_name}"
                except (json.JSONDecodeError, TypeError):
                    # Fallback to regular body if JSON parsing fails
                    record.display_body = record.body
            else:
                record.display_body = record.body

    def get_tool_data(self):
        """Parse and return tool data from JSON body for tool messages."""
        self.ensure_one()
        if self.llm_role == 'tool':
            try:
                return json.loads(self.body)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    def get_tool_call_id(self):
        """Get tool_call_id from tool data."""
        tool_data = self.get_tool_data()
        return tool_data.get('tool_call_id') if tool_data else None

    def get_tool_call_definition(self):
        """Get tool_call definition from tool data."""
        tool_data = self.get_tool_data()
        return tool_data.get('tool_call') if tool_data else None

    def get_tool_call_result(self):
        """Get tool_call result from tool data."""
        tool_data = self.get_tool_data()
        if tool_data:
            if 'result' in tool_data:
                return tool_data['result']
            elif 'error' in tool_data:
                return {'error': tool_data['error']}
        return None

    def get_tool_call_result_is_error(self):
        """Check if tool call result is an error."""
        tool_data = self.get_tool_data()
        return tool_data and tool_data.get('status') == 'error'

    def get_tool_name(self):
        """Get tool name from tool data."""
        tool_data = self.get_tool_data()
        return tool_data.get('tool_name') if tool_data else None

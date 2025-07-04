import json
import logging

from odoo import models, tools

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"

    def openai_format_message(self):
        """Provider-specific formatting for OpenAI."""
        self.ensure_one()
        body = self.body
        if body:
            body = tools.html2plaintext(body)

        if self.is_llm_user_message():
            formatted_message = {"role": "user"}
            if body:
                formatted_message["content"] = body
            return formatted_message

        elif self.is_llm_assistant_message():
            formatted_message = {"role": "assistant"}
            if body:
                formatted_message["content"] = body
            
            # For assistant messages, we don't store tool_calls in the message anymore
            # Tool calls are stored as separate tool messages
            # This section is kept for backward compatibility but won't be used
            
            return formatted_message

        elif self.is_llm_tool_result_message():
            try:
                tool_data = json.loads(self.body)
                if tool_data.get("type") == "tool_execution":
                    tool_call_id = tool_data.get("tool_call_id")
                    if not tool_call_id:
                        _logger.warning(
                            f"OpenAI Format: Skipping tool result message {self.id}: missing tool_call_id."
                        )
                        return None
                    
                    # Get result content
                    if "result" in tool_data:
                        content = json.dumps(tool_data["result"])
                    elif "error" in tool_data:
                        content = json.dumps({"error": tool_data["error"]})
                    else:
                        content = ""
                    
                    formatted_message = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": content,
                    }
                    return formatted_message
            except (json.JSONDecodeError, TypeError):
                _logger.warning(
                    f"OpenAI Format: Skipping tool result message {self.id}: invalid JSON in body."
                )
                return None
        else:
            return None

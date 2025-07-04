import json
import logging

from odoo import models, tools

from ..utils.ollama_tool_call_id_utils import OllamaToolCallIdUtils

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"

    def ollama_format_message(self):
        """Provider-specific formatting for Ollama."""
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
            content = tools.html2plaintext(self.body) if self.body else ""
            if content:
                formatted_message["content"] = content

            # For assistant messages, we don't store tool_calls in the message anymore
            # Tool calls are stored as separate tool messages
            # This section is kept for backward compatibility but won't be used

            return formatted_message

        elif self.is_llm_tool_result_message():
            try:
                tool_data = json.loads(self.body)
                if tool_data.get("type") == "tool_execution":
                    tool_name = tool_data.get("tool_name")
                    if not tool_name:
                        # Fallback to extracting from tool_call_id
                        tool_call_id = tool_data.get("tool_call_id")
                        if tool_call_id:
                            tool_name = OllamaToolCallIdUtils.extract_tool_name_from_id(tool_call_id)
                    
                    if not tool_name:
                        _logger.warning(
                            f"Ollama Format: Skipping tool result message {self.id}: missing tool_name."
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
                        "name": tool_name,
                        "content": content,
                    }
                    return formatted_message
            except (json.JSONDecodeError, TypeError):
                _logger.warning(
                    f"Ollama Format: Skipping tool result message {self.id}: invalid JSON in body."
                )
                return None
        else:
            return None

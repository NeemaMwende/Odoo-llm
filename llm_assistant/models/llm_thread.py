import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    assistant_id = fields.Many2one(
        "llm.assistant",
        string="Assistant",
        ondelete="restrict",
        help="The assistant used for this thread",
    )

    @api.onchange("assistant_id")
    def _onchange_assistant_id(self):
        """Update provider, model and tools when assistant changes"""
        if self.assistant_id:
            self.provider_id = self.assistant_id.provider_id
            self.model_id = self.assistant_id.model_id
            self.tool_ids = self.assistant_id.tool_ids
            self.prompt_id = self.assistant_id.prompt_id

    def set_assistant(self, assistant_id):
        """Set the assistant for this thread and update related fields

        Args:
            assistant_id (int): The ID of the assistant to set

        Returns:
            bool: True if successful, False otherwise
        """
        self.ensure_one()

        # If assistant_id is False or 0, just clear the assistant
        if not assistant_id:
            return self.write({"assistant_id": False})

        # Get the assistant record
        assistant = self.env["llm.assistant"].browse(assistant_id)
        if not assistant.exists():
            return False

        # Update the thread with the assistant and related fields
        update_vals = {
            "assistant_id": assistant_id,
            "tool_ids": [(6, 0, assistant.tool_ids.ids)],
        }
        if assistant.provider_id.id:
            update_vals["provider_id"] = assistant.provider_id.id
        if assistant.model_id.id:
            update_vals["model_id"] = assistant.model_id.id
        if assistant.prompt_id.id:
            update_vals["prompt_id"] = assistant.prompt_id.id
        return self.write(update_vals)

    def action_open_thread(self):
        """Open the thread in the chat client interface

        Returns:
            dict: Action to open the thread in the chat client
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "llm_thread.chat_client_action",
            "params": {
                "default_active_id": self.id,
            },
            "context": {
                "active_id": self.id,
            },
            "target": "current",
        }

    def get_context(self, base_context=None):
        """
        Get the context for prompt rendering, including assistant's default values.

        Args:
            base_context (dict): Additional context from caller (optional)

        Returns:
            dict: Context for prompt rendering
        """
        self.ensure_one()

        # Get the base context from parent (this includes thread context like related_record, etc.)
        context = super().get_context(base_context or {})

        # If we have an assistant with default values, add them to the context
        if self.assistant_id:
            # Get assistant's evaluated default values using the current context
            assistant_defaults = self.assistant_id.get_evaluated_default_values(context)

            # Merge assistant defaults into context
            # Assistant defaults are added first, so thread context takes precedence
            if assistant_defaults:
                merged_context = {**assistant_defaults, **context}
                return merged_context

        return context

    @api.model
    def get_thread_by_id(self, thread_id):
        """Get a thread record by its ID

        Args:
            thread_id (int): ID of the thread

        Returns:
            tuple: (thread, error_response)
                  If successful, error_response will be None
                  If error, thread will be None
        """
        thread = self.browse(int(thread_id))
        if not thread.exists():
            return None, {"success": False, "error": "Thread not found"}
        return thread, None

    @api.model
    def get_thread_and_assistant(self, thread_id, assistant_id=False):
        """Get thread and assistant records by their IDs

        Args:
            thread_id (int): ID of the thread
            assistant_id (int, optional): ID of the assistant, or False to clear

        Returns:
            tuple: (thread, assistant, error_response)
                  If successful, error_response will be None
                  If error, thread and/or assistant will be None
        """
        # Get thread
        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return None, None, error

        # If no assistant_id, return just the thread
        if not assistant_id:
            return thread, None, None

        # Get assistant from the assistant model
        assistant, error = self.env["llm.assistant"].get_assistant_by_id(assistant_id)
        if error:
            return thread, None, error

        return thread, assistant, None

    def _process_tool_calls(self, assistant_msg):
        """Override _process_tool_calls to implement circuit breaker using assistant's tool_calls_max"""
        self.ensure_one()
        
        # Get the tool calls max from the assistant, default to 5 if no assistant
        tool_calls_max = self.assistant_id.tool_calls_max if self.assistant_id else 5
        
        # Count recent consecutive assistant messages with tool calls to detect loops
        # We need to look at messages BEFORE the current one to count previous iterations
        recent_messages = self.get_message_history_recordset(order="DESC", limit=20)
        consecutive_tool_calls = 0
        
        for msg in recent_messages:
            # Skip the current message since we're about to process it
            if msg.id == assistant_msg.id:
                continue
                
            if msg.is_llm_assistant_message() and msg.tool_calls:
                consecutive_tool_calls += 1
                _logger.debug(f"Thread {self.id}: Found assistant message {msg.id} with tool calls (count: {consecutive_tool_calls})")
            elif msg.is_llm_user_message():
                # Stop counting when we hit a user message (new conversation turn)
                _logger.debug(f"Thread {self.id}: Hit user message {msg.id}, stopping count")
                break
            elif msg.is_llm_assistant_message() and msg.body and msg.body.strip():
                # Stop counting when we hit an assistant message with meaningful content
                _logger.debug(f"Thread {self.id}: Hit assistant message {msg.id} with content, stopping count")
                break
            # Continue through tool result messages without stopping the count
        
        # Circuit breaker: if too many consecutive tool calling assistant messages, clear tool_calls and stop
        if consecutive_tool_calls >= tool_calls_max:
            _logger.warning(
                f"Thread {self.id}: Circuit breaker activated! Found {consecutive_tool_calls} consecutive assistant messages with tool calls, "
                f"which exceeds the assistant's limit of {tool_calls_max}. Clearing tool_calls from message {assistant_msg.id}"
            )
            assistant_msg.write({"tool_calls": None})
            return assistant_msg
        
        # If we're under the limit, proceed with normal tool processing
        _logger.info(
            f"Thread {self.id}: Processing tool calls ({consecutive_tool_calls}/{tool_calls_max} consecutive assistant tool call messages)"
        )
        
        # Call the parent method for normal processing
        return (yield from super()._process_tool_calls(assistant_msg))

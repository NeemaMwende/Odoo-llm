import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RelatedRecordProxy:
    """
    A proxy object that provides clean access to related record fields in Jinja templates.
    Usage in templates: {{ related_record.get_field('field_name', 'default_value') }}
    When called directly, returns JSON with model name, id, and display name.
    """

    def __init__(self, record):
        self._record = record

    def get_field(self, field_name, default=""):
        """
        Get a field value from the related record.

        Args:
            field_name (str): The field name to access
            default: Default value if field doesn't exist or is empty

        Returns:
            The field value, or default if not available
        """
        if not self._record:
            return default

        try:
            if hasattr(self._record, field_name):
                value = getattr(self._record, field_name)

                # Handle different field types
                if value is None:
                    return default
                elif isinstance(value, bool):
                    return value  # Keep as boolean for Jinja
                elif hasattr(value, 'name'):  # Many2one field
                    return value.name
                elif hasattr(value, 'mapped'):  # Many2many/One2many field
                    return value.mapped('name')
                else:
                    return value
            else:
                _logger.debug("Field '%s' not found on record %s", field_name, self._record)
                return default

        except Exception as e:
            _logger.error("Error getting field '%s' from record: %s", field_name, str(e))
            return default

    def __getattr__(self, name):
        """Allow direct attribute access as fallback"""
        return self.get_field(name)

    def __bool__(self):
        """Return True if we have a record"""
        return bool(self._record)

    def __str__(self):
        """When called by itself, return JSON of model name, id, and display name"""
        if not self._record:
            return json.dumps({
                "model": None,
                "id": None,
                "display_name": None
            })

        return json.dumps({
            "model": self._record._name,
            "id": self._record.id,
            "display_name": getattr(self._record, 'display_name', str(self._record))
        })

    def __repr__(self):
        """Same as __str__ for consistency"""
        return self.__str__()


class LLMThread(models.Model):
    _inherit = "llm.thread"

    assistant_id = fields.Many2one(
        "llm.assistant",
        string="Assistant",
        ondelete="restrict",
        help="The assistant used for this thread",
    )
    
    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt for workflow",
        ondelete="restrict",
        tracking=True,
        help="Prompt to use for workflow",
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
        Get the context to pass to prompt rendering with thread-specific enhancements.
        This is the canonical method for creating prompt context in both production and testing.

        Args:
            base_context (dict): Additional context from caller (optional)

        Returns:
            dict: Context ready for prompt rendering
        """
        context = {
            **super().get_context(base_context or {}),
            'thread_id': self.id,
        }

        try:
            related_record = self.env[self.model].browse(self.res_id)
            if related_record:
                context['related_record'] = RelatedRecordProxy(related_record)
                context['related_model_name'] = self.model
                context['related_model_id'] = self.model  # Keep for backward compatibility
                context['related_res_id'] = self.res_id
            else:
                context['related_record'] = None
                context['related_model_name'] = None
                context['related_model_id'] = None
                context['related_res_id'] = None
        except Exception as e:
            _logger.warning("Error accessing related record %s,%s: %s", self.model, self.res_id, e)

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

    def merge_message_lists(self, source_messages, target_messages):
        """Merge two lists of messages, handling system messages appropriately"""
        if not source_messages:
            return target_messages

        if not target_messages:
            return source_messages.copy()

        source_messages_copy = source_messages.copy()

        # Check for system messages to avoid duplicates
        system_messages_in_source = [
            msg for msg in source_messages_copy if msg.get("role") == "system"
        ]
        system_messages_in_target = [
            msg for msg in target_messages if msg.get("role") == "system"
        ]

        if system_messages_in_source and system_messages_in_target:
            # Both have system messages, merge them
            for source_msg in system_messages_in_source:
                for target_msg in system_messages_in_target:
                    source_content = self._extract_message_content(source_msg)
                    target_content = self._extract_message_content(target_msg)

                    # Merge the content
                    merged_content = f"{source_content}\n\n{target_content}"

                    # Update target message with merged content
                    if isinstance(target_msg.get("content"), list):
                        target_msg["content"][0]["text"] = merged_content
                    else:
                        target_msg["content"] = merged_content

                # Remove the source system message as we've merged it
                source_messages_copy.remove(source_msg)

        # Now add any remaining source messages at the beginning
        return source_messages_copy + target_messages

    def _extract_message_content(self, message):
        """Extract text content from a message regardless of format"""
        content = message.get("content", "")

        if isinstance(content, list) and len(content) > 0:
            return content[0].get("text", "")
        elif isinstance(content, str):
            return content
        else:
            return ""

    def get_prepend_messages(self):
        """Hook: return a list of formatted messages to prepend to the conversation."""
        self.ensure_one()
        messages = super().get_prepend_messages()

        if self.prompt_id:
            try:

                # Get messages from the prompt with enhanced context
                prompt_messages = self.prompt_id.get_messages(self.get_context())

                if prompt_messages:
                    messages = self.merge_message_lists(prompt_messages, messages)
                    _logger.info("Added %d messages from prompt '%s'", len(prompt_messages), self.prompt_id.name)

            except Exception as e:
                _logger.error("Error getting messages from prompt '%s': %s", self.prompt_id.name, str(e))
                # Continue without prompt messages rather than failing completely
                self.message_post(
                    body=f"Warning: Could not load prompt messages from '{self.prompt_id.name}': {str(e)}"
                )

        return messages

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

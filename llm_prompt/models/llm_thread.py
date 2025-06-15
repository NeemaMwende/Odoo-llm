import json
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class RelatedRecordProxy:
    """
    A proxy object that provides clean access to related record fields in Jinja templates.
    Usage in templates: {{ related_record.get_field('field_name', 'default_value') }}
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


class LLMThreadPrompt(models.Model):
    _inherit = "llm.thread"

    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt for workflow",
        ondelete="restrict",
        tracking=True,
        help="Prompt to use for workflow",
    )

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

    def _get_prompt_context(self, base_context=None):
        """
        Get the context to pass to prompt rendering with simplified related_record access.

        Args:
            base_context (dict): Base context from the caller

        Returns:
            dict: Enhanced context for prompt rendering
        """
        context = dict(base_context or {})

        # Add thread-specific context
        context['thread_id'] = self.id

        # Add simplified related_record object
        if self.related_record:
            context['related_record'] = RelatedRecordProxy(self.related_record)
        else:
            context['related_record'] = RelatedRecordProxy(None)  # Empty proxy

        return context

    def _get_prepend_messages(self, context=None):
        """Hook: return a list of formatted messages to prepend to the conversation."""
        context = context or {}
        self.ensure_one()

        # Get base messages from parent class
        messages = super()._get_prepend_messages(context=context)

        if self.prompt_id:
            try:
                # Get enhanced context for prompt rendering
                prompt_context = self._get_prompt_context(context)

                # Get messages from the prompt with enhanced context
                prompt_messages = self.prompt_id.get_messages(prompt_context)

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

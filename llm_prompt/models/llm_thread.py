import json
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


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
        """Merge two lists of messages, handling system messages appropriately

        This helper method merges two lists of messages, ensuring that system messages
        are properly combined without duplication.

        Args:
            source_messages (list): The source list of messages to merge from
            target_messages (list): The target list of messages to merge into

        Returns:
            list: The merged list of messages
        """
        if not source_messages:
            return target_messages

        if not target_messages:
            return (
                source_messages.copy()
            )  # Return a copy to avoid modifying the original

        # Make a copy of source messages to avoid modifying the original
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
                    # Handle different content formats
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
            # Handle new format with content array
            return content[0].get("text", "")
        elif isinstance(content, str):
            # Handle old format with direct content string
            return content
        else:
            return ""

    # override to include prompt messages
    def _get_prepend_messages(self, context=None):
        """Hook: return a list of formatted messages to prepend to the conversation.
        Override in other modules if needed.

        Returns:
            list: List of message dictionaries in the format:
                [{"role": "system", "content": [{"type": "text", "text": "..."}]},
                 {"role": "user", "content": [{"type": "text", "text": "..."}]},
                 ...]
        """
        context = context or {}
        self.ensure_one()
        # Get base messages from parent class
        messages = super()._get_prepend_messages(context=context)

        if self.prompt_id:
            context["thread_id"] = self.id
            context["related_record"] = json.dumps(
                {
                    "model": self.related_record._name,
                    "id": self.related_record.id,
                    "display_name": self.related_record.display_name,
                }
            ) if self.related_record else False
            context["get_related_field"] = self.get_related_field
            # Use the prompt to get messages with the new context
            prompt_messages = self.prompt_id.get_messages(context)
            if prompt_messages:
                messages = self.merge_message_lists(prompt_messages, messages)
                _logger.info("Added %d messages from prompt", len(prompt_messages))

        return messages

    def get_related_field(self, field_name, key_name=None):
        """
        Access fields or dictionary keys from a related record.

        Args:
            field_name (str): The field name to access
            key_name (str, optional): If the field is a dictionary, the key to access
            related_record (Model, optional): The record to access.

        Returns:
            str: The value of the field/key or an empty string if not available
        """
        # If we still don't have a related record, return empty string
        if not self.related_record:
            _logger.info(
                f"No related record available, returning empty value for {field_name}"
            )
            return ""

        # Access the field
        if hasattr(self.related_record, field_name):
            try:
                attr_value = getattr(self.related_record, field_name)

                if (
                        key_name is not None
                ):  # We want to access an item from this attribute
                    if isinstance(attr_value, dict):
                        if key_name in attr_value:
                            final_value = attr_value[key_name]
                        else:
                            _logger.warning(
                                "Key '%s' not found in dictionary field '%s'",
                                key_name,
                                field_name,
                            )
                            return ""  # Return empty string instead of error message
                    else:
                        _logger.warning(
                            "Field '%s' is not a dictionary, cannot access key '%s'",
                            field_name,
                            key_name,
                        )
                        return ""  # Return empty string instead of error message
                else:  # No key, just return the attribute value
                    final_value = attr_value

                # Convert to string with proper JSON handling for booleans
                if isinstance(final_value, bool):
                    return "true" if final_value else "false"
                return final_value

            except Exception as e:
                _logger.error(
                    "Error getting field %s (key: %s) from record: %s",
                    field_name,
                    key_name,
                    str(e),
                )
                return ""  # Return empty string instead of error message
        else:
            _logger.warning("Record doesn't have field: %s", field_name)
            return ""  # Return empty string instead of error message

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

    def get_related_field(self, field_name, key_name=None):
        """
        Access fields or dictionary keys from a related record.

        Args:
            field_name (str): The field name to access
            key_name (str, optional): If the field is a dictionary, the key to access

        Returns:
            str: The value of the field/key or an empty string if not available
        """
        # If we don't have a related record, return empty string
        if not self.related_record:
            _logger.debug(
                f"No related record available, returning empty value for {field_name}"
            )
            return ""

        # Access the field
        if hasattr(self.related_record, field_name):
            try:
                attr_value = getattr(self.related_record, field_name)

                if key_name is not None:  # We want to access an item from this attribute
                    if isinstance(attr_value, dict):
                        if key_name in attr_value:
                            final_value = attr_value[key_name]
                        else:
                            _logger.debug(
                                "Key '%s' not found in dictionary field '%s'",
                                key_name,
                                field_name,
                            )
                            return ""
                    else:
                        _logger.debug(
                            "Field '%s' is not a dictionary, cannot access key '%s'",
                            field_name,
                            key_name,
                        )
                        return ""
                else:  # No key, just return the attribute value
                    final_value = attr_value

                # Convert to string with proper JSON handling for booleans
                if isinstance(final_value, bool):
                    return "true" if final_value else "false"
                elif final_value is None:
                    return ""
                else:
                    return str(final_value)

            except Exception as e:
                _logger.error(
                    "Error getting field %s (key: %s) from record: %s",
                    field_name,
                    key_name,
                    str(e),
                )
                return ""
        else:
            _logger.debug("Record doesn't have field: %s", field_name)
            return ""

    def _get_template_functions(self):
        """
        Get template functions to provide to prompt rendering.
        Override this method in other modules to add more functions.

        Returns:
            dict: Dictionary of function name -> callable mappings
        """
        return {
            'get_related_field': self.get_related_field,
            'get_related_record': self.get_related_field,  # Alias for backward compatibility
        }

    def _get_prompt_context(self, base_context=None):
        """
        Get the context to pass to prompt rendering.
        Override this method in other modules to add more context.

        Args:
            base_context (dict): Base context from the caller

        Returns:
            dict: Enhanced context for prompt rendering
        """
        context = dict(base_context or {})

        # Add thread-specific context
        context['thread_id'] = self.id

        # Add related record information if available
        if self.related_record:
            context['related_record'] = json.dumps({
                "model": self.related_record._name,
                "id": self.related_record.id,
                "display_name": self.related_record.display_name,
            })

        # Add template functions to the context
        context['template_functions'] = self._get_template_functions()

        return context

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
            try:
                # Get enhanced context for prompt rendering (includes template_functions)
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

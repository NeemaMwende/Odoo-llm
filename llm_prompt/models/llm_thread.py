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

    # override to include prompt messages
    def _get_prepend_messages(self):
        """Hook: return a list of formatted messages to prepend to the conversation.
        Override in other modules if needed.
        
        Returns:
            list: List of message dictionaries in the format:
                [{"role": "system", "content": "..."},
                 {"role": "user", "content": "..."},
                 ...]
        """
        self.ensure_one()
        # Get base messages from parent class
        messages = super()._get_prepend_messages()
        
        # Get messages from the prompt if available
        if self.prompt_id:
            # Create a context with the thread_id
            context = dict(self.env.context, thread_id=self.id)
            # Use the prompt to get messages with the new context
            prompt_messages = self.with_context(context).prompt_id.get_messages({})
            if prompt_messages:
                # If we already have messages, merge them with existing messages
                if messages:
                    # Check for system messages to avoid duplicates
                    system_messages_in_prompt = [msg for msg in prompt_messages if msg.get("role") == "system"]
                    system_messages_in_existing = [msg for msg in messages if msg.get("role") == "system"]
                    
                    if system_messages_in_prompt and system_messages_in_existing:
                        # Both have system messages, merge them
                        for prompt_msg in system_messages_in_prompt:
                            for exist_msg in system_messages_in_existing:
                                exist_msg["content"] = f"{prompt_msg['content']}\n\n{exist_msg['content']}"
                            # Remove the prompt system message as we've merged it
                            prompt_messages.remove(prompt_msg)
                    
                    # Now add any remaining prompt messages at the beginning
                    messages = prompt_messages + messages
                else:
                    # No existing messages, use the prompt messages directly
                    messages = prompt_messages
                
                _logger.info("Added %d messages from prompt", len(prompt_messages))
                
        return messages

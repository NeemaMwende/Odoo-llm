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
    
    # override to include assistant's system prompt
    def _get_system_prompt(self):
        """Hook: return a system prompt for chat. Override in other modules. If needed"""
        self.ensure_one()
        system_prompt = super()._get_system_prompt()
        current_prompt = None
        if self.prompt_id:
            
            # Create a context with the thread_id
            context = dict(self.env.context, thread_id=self.id)
            # Use the prompt with the new context
            current_prompt = self.with_context(context).prompt_id.get_formatted_system_prompt({})

        if current_prompt and system_prompt:
            system_prompt = f"{current_prompt}\n\n{system_prompt}"
        elif current_prompt:
            system_prompt = current_prompt
        _logger.info("System prompt: %s", system_prompt)
        return system_prompt

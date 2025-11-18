from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "llm.invoice.assistant.mixin"]

    def action_process_with_ai(self):
        """
        Prepare LLM thread with Invoice Analysis Assistant.
        Uses the generic mixin to create/find thread and set assistant.
        Frontend will then click the AI button to open the chat.
        """
        return self.action_open_llm_assistant("invoice_analyzer")

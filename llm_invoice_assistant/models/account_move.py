import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_process_with_ai(self):
        """
        Prepare LLM thread with Invoice Analysis Assistant.
        Creates/finds thread for this invoice and sets the assistant.
        Frontend will then click the AI button to open the chat.
        """
        self.ensure_one()

        _logger.info(
            "=== Process with AI started for invoice ID: %s, Name: %s ===",
            self.id,
            self.name,
        )

        # 1. Find existing thread or create new one
        _logger.info("Step 1: Looking for existing thread...")
        thread = self.env["llm.thread"].search(
            [("model", "=", "account.move"), ("res_id", "=", self.id)], limit=1
        )

        if thread:
            _logger.info("Found existing thread ID: %s", thread.id)
        else:
            _logger.info("No existing thread found, creating new one...")

        if not thread:
            # Find default chat model or fallback to first available
            _logger.info("Looking for default chat model...")
            default_model = self.env["llm.model"].search(
                [
                    ("model_use", "in", ["chat", "multimodal"]),
                    ("default", "=", True),
                    ("active", "=", True),
                ],
                limit=1,
            )

            if default_model:
                _logger.info(
                    "Found default model: %s (Provider: %s)",
                    default_model.name,
                    default_model.provider_id.name,
                )
            else:
                _logger.info("No default model found, looking for first available...")

            if not default_model:
                # Fallback: Get first provider and its first chat model
                _logger.info("Looking for first available provider...")
                provider = self.env["llm.provider"].search(
                    [("active", "=", True)], limit=1
                )
                if not provider:
                    _logger.error("No active LLM provider found!")
                    raise UserError(
                        "No active LLM provider found. Please configure a provider first."
                    )

                _logger.info("Found provider: %s", provider.name)
                _logger.info("Looking for first chat model for this provider...")
                default_model = self.env["llm.model"].search(
                    [
                        ("provider_id", "=", provider.id),
                        ("model_use", "in", ["chat", "multimodal"]),
                        ("active", "=", True),
                    ],
                    limit=1,
                )

            if not default_model:
                _logger.error("No active chat model found!")
                raise UserError(
                    "No active chat model found. Please configure a model first."
                )

            _logger.info(
                "Creating new thread with Provider: %s, Model: %s",
                default_model.provider_id.name,
                default_model.name,
            )

            # Create new thread
            thread = self.env["llm.thread"].create(
                {
                    "name": f"AI Chat - {self._name} #{self.id}",
                    "model": "account.move",
                    "res_id": self.id,
                    "provider_id": default_model.provider_id.id,
                    "model_id": default_model.id,
                }
            )
            _logger.info("Thread created successfully with ID: %s", thread.id)

        # 2. Find and set Invoice Analysis Assistant
        _logger.info("Step 2: Looking for Invoice Analysis Assistant...")
        assistant = self.env["llm.assistant"].search(
            [("code", "=", "invoice_analyzer")], limit=1
        )

        if assistant:
            _logger.info("Found assistant: %s (ID: %s)", assistant.name, assistant.id)
            if not thread.assistant_id:
                _logger.info("Setting assistant on thread...")
                thread.assistant_id = assistant.id
                _logger.info("Assistant set successfully")
            else:
                _logger.info(
                    "Thread already has assistant: %s", thread.assistant_id.name
                )
        else:
            _logger.warning("Invoice Analysis Assistant not found!")

        _logger.info(
            "=== Process with AI completed. Thread ID: %s, Assistant: %s ===",
            thread.id,
            thread.assistant_id.name if thread.assistant_id else "None",
        )

        # 3. Return True - frontend will click AI button via onclick
        return True

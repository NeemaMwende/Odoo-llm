import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMAssistantMixin(models.AbstractModel):
    """
    Mixin to add AI assistant functionality to any model.
    Provides a generic method to open LLM threads with specific assistants.

    Usage:
        class MyModel(models.Model):
            _inherit = ['my.model', 'llm.invoice.assistant.mixin']

            def action_my_ai_button(self):
                return self.action_open_llm_assistant('my_assistant_code')
    """

    _name = "llm.invoice.assistant.mixin"
    _description = "LLM Invoice Assistant Mixin"

    def action_open_llm_assistant(self, assistant_code=None, **kwargs):
        """
        Generic method to open AI assistant for current record.
        Creates/finds thread, sets assistant, and prepares for frontend to open AI chat.

        Args:
            assistant_code: Code of the assistant to use (e.g., 'invoice_analyzer').
                           If not provided, tries to get from context.
            **kwargs:
                - pre_action: Method name to call before opening (e.g., '_validate_state')
                - post_action: Method name to call after opening (e.g., '_log_interaction')

        Returns:
            True (for frontend onclick to continue)

        Raises:
            UserError: If no provider/model found or if pre_action raises
        """
        self.ensure_one()

        # Get assistant code from parameter or context
        if not assistant_code:
            assistant_code = self.env.context.get("assistant_code")

        if not assistant_code:
            raise UserError(
                "No assistant code provided. Please specify assistant_code parameter or context."
            )

        _logger.info(
            "=== Opening AI assistant '%s' for %s ID: %s ===",
            assistant_code,
            self._name,
            self.id,
        )

        # Call pre-action hook if provided
        pre_action = kwargs.get("pre_action")
        if pre_action:
            _logger.info("Calling pre-action hook: %s", pre_action)
            if hasattr(self, pre_action):
                getattr(self, pre_action)()
            else:
                _logger.warning("Pre-action method '%s' not found", pre_action)

        # Find existing thread or create new one
        thread = self._find_or_create_llm_thread()

        # Find and set assistant
        self._set_assistant_on_thread(thread, assistant_code)

        # Call post-action hook if provided
        post_action = kwargs.get("post_action")
        if post_action:
            _logger.info("Calling post-action hook: %s", post_action)
            if hasattr(self, post_action):
                getattr(self, post_action)()
            else:
                _logger.warning("Post-action method '%s' not found", post_action)

        _logger.info(
            "=== AI assistant ready. Thread ID: %s, Assistant: %s ===",
            thread.id,
            thread.assistant_id.name if thread.assistant_id else "None",
        )

        return True

    def _find_or_create_llm_thread(self):
        """
        Find existing thread for this record or create a new one.

        Returns:
            llm.thread: The thread record
        """
        _logger.info("Step 1: Looking for existing thread...")
        thread = self.env["llm.thread"].search(
            [("model", "=", self._name), ("res_id", "=", self.id)], limit=1
        )

        if thread:
            _logger.info("Found existing thread ID: %s", thread.id)
            return thread

        _logger.info("No existing thread found, creating new one...")

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

            # Fallback: Get first provider and its first chat model
            _logger.info("Looking for first available provider...")
            provider = self.env["llm.provider"].search([("active", "=", True)], limit=1)
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
                "model": self._name,
                "res_id": self.id,
                "provider_id": default_model.provider_id.id,
                "model_id": default_model.id,
            }
        )
        _logger.info("Thread created successfully with ID: %s", thread.id)

        return thread

    def _set_assistant_on_thread(self, thread, assistant_code):
        """
        Find assistant by code and set it on the thread.

        Args:
            thread: llm.thread record
            assistant_code: Code of the assistant to find
        """
        _logger.info("Step 2: Looking for assistant with code '%s'...", assistant_code)
        assistant = self.env["llm.assistant"].search(
            [("code", "=", assistant_code)], limit=1
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
            _logger.warning("Assistant with code '%s' not found!", assistant_code)

import logging

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.openai.models.openai_client import openai

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    def openai_upload_file(self, file_tuple, purpose="fine-tune"):
        """Upload a file to OpenAI"""
        response = self.client.files.create(file=file_tuple, purpose=purpose)
        return response
        

    def upload_file(self, file_tuple, purpose="fine-tune"):
        """Upload a file to the provider"""
        return self._dispatch("upload_file", file_tuple, purpose)

    # --- Fine-tuning Job Creation --- 

    def openai_create_fine_tuning_job(self, training_file_id, model_name, hyperparameters=None):
        """Create an OpenAI fine-tuning job."""
        self.ensure_one()
        
        hyperparameters = hyperparameters or {}
        hyperparams_cleaned = {k: v for k, v in hyperparameters.items() if v is not None}

        response = self.client.fine_tuning.jobs.create(
            training_file=training_file_id,
            model=model_name,
            # Pass None if cleaned dict is empty, otherwise pass the dict
            hyperparameters=hyperparams_cleaned if hyperparams_cleaned else None, 
        )
        _logger.info(f"Fine-tuning job created successfully for provider '{self.name}'. Job ID: {response.id}")
        return response
        

    def create_fine_tuning_job(self, training_file_id, model_name, hyperparameters=None):
        """Create a fine-tuning job with the provider."""
        return self._dispatch("create_fine_tuning_job", training_file_id, model_name, hyperparameters)
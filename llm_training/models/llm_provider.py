import logging

from odoo import models

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

    def openai_retrieve_fine_tuning_job(self, job_id):
        """Retrieve an OpenAI fine-tuning job."""
        self.ensure_one()
        response = self.client.fine_tuning.jobs.retrieve(job_id)
        return response
        
    def retrieve_fine_tuning_job(self, job_id):
        """Retrieve a fine-tuning job with the provider."""
        return self._dispatch("retrieve_fine_tuning_job", job_id)

    def cancel_fine_tuning_job(self, job_id):
        """Cancel a fine-tuning job with the provider."""
        return self._dispatch("cancel_fine_tuning_job", job_id)
    
    def openai_cancel_fine_tuning_job(self, job_id):
        """Cancel an OpenAI fine-tuning job."""
        self.ensure_one()
        response = self.client.fine_tuning.jobs.cancel(job_id)
        return response
    
    def retrieve_model(self, model_id):
        """Retrieve a model with the provider."""
        return self._dispatch("retrieve_model", model_id)
        
    def openai_retrieve_model(self, model_id):
        """Retrieve a model with the provider."""
        self.ensure_one()
        response = self.client.models.retrieve(model_id)
        return response
    def format_fine_tune_metrics(self, response):
        """Format fine-tuning metrics to a standardized format."""
        return self._dispatch("format_fine_tune_metrics", response)

    def openai_format_fine_tune_metrics(self, response):
        """Format OpenAI fine-tuning metrics to a standardized format.
        
        Args:
            response: OpenAI fine-tuning response object
            
        Returns:
            dict: Standardized metrics dictionary
        """
        metrics = {}
        
        # Extract basic job information
        for field in ['id', 'model', 'status', 'created_at', 'finished_at', 'trained_tokens']:
            if hasattr(response, field):
                metrics[field] = getattr(response, field)
            
        # Extract file information
        for field in ['training_file', 'validation_file', 'result_files']:
            if hasattr(response, field) and getattr(response, field):
                metrics[field] = getattr(response, field)
                
        # Calculate training duration if available
        if hasattr(response, 'created_at') and hasattr(response, 'finished_at') and response.finished_at:
            metrics['training_duration_seconds'] = response.finished_at - response.created_at
            
        return metrics
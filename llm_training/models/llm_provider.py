from odoo import models


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    def upload_file(self, file_tuple, purpose="fine-tune"):
        """Upload a file to the provider"""
        return self._dispatch("upload_file", file_tuple, purpose)

    def create_fine_tuning_job(
        self, training_file_id, model_name, hyperparameters=None
    ):
        """Create a fine-tuning job with the provider."""
        return self._dispatch(
            "create_fine_tuning_job", training_file_id, model_name, hyperparameters
        )

    def retrieve_fine_tuning_job(self, job_id):
        """Retrieve a fine-tuning job with the provider."""
        return self._dispatch("retrieve_fine_tuning_job", job_id)

    def cancel_fine_tuning_job(self, job_id):
        """Cancel a fine-tuning job with the provider."""
        return self._dispatch("cancel_fine_tuning_job", job_id)

    def format_fine_tune_metrics(self, response):
        """Format fine-tuning metrics to a standardized format."""
        return self._dispatch("format_fine_tune_metrics", response)

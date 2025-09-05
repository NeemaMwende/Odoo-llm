import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    @api.model
    def _get_available_services(self):
        services = super()._get_available_services()
        return services + [("letta", "Letta")]

    def letta_get_client(self):
        """Get Letta client instance"""
        try:
            from letta_client import Letta
        except ImportError as err:
            raise UserError(
                "Letta client not installed. Please install with: pip install letta-client"
            ) from err

        # Determine if using local or cloud
        if self.api_base and "localhost" in self.api_base:
            # Local server - no auth required
            return Letta(base_url=self.api_base)
        else:
            # Cloud server - requires token and project
            if not self.api_key:
                raise UserError("API key is required for Letta Cloud connection")
            
            # Use api_base as project if provided, otherwise default
            project = "default-project"
            if self.api_base and self.api_base != "https://api.letta.com/v1":
                project = self.api_base
                
            return Letta(token=self.api_key, project=project)

    def letta_models(self, model_id=None):
        """List available models from Letta"""
        client = self.letta_get_client()
        
        try:
            models_response = client.models.list()
            
            # Convert Letta model format to our standard format
            models = []
            for model in models_response:
                model_data = {
                    "name": model.model,
                    "provider": model.provider_name if hasattr(model, 'provider_name') else "letta",
                    "context_window": getattr(model, 'context_window', None),
                    "model_endpoint_type": getattr(model, 'model_endpoint_type', None),
                    "temperature": getattr(model, 'temperature', None),
                    "max_tokens": getattr(model, 'max_tokens', None),
                }
                
                # Filter by specific model if requested
                if model_id and model_data["name"] != model_id:
                    continue
                    
                models.append(model_data)
                
            return models
            
        except Exception as e:
            _logger.error(f"Failed to fetch models from Letta: {str(e)}")
            raise UserError(f"Failed to fetch models from Letta: {str(e)}") from e

    # Placeholder methods - not implemented yet
    def letta_chat(self, messages, model=None, stream=False, **kwargs):  # pylint: disable=unused-argument
        """Chat completion - not implemented yet"""
        raise NotImplementedError(
            "Letta chat functionality is not yet implemented. "
            "This provider currently only supports model fetching."
        )

    def letta_embedding(self, texts, model=None):  # pylint: disable=unused-argument
        """Text embedding - not implemented yet"""
        raise NotImplementedError(
            "Letta embedding functionality is not yet implemented. "
            "This provider currently only supports model fetching."
        )

    def letta_generate(self, input_data, model=None, stream=False, **kwargs):  # pylint: disable=unused-argument
        """Content generation - not implemented yet"""
        raise NotImplementedError(
            "Letta generation functionality is not yet implemented. "
            "This provider currently only supports model fetching."
        )

    def letta_format_tools(self, tools):  # pylint: disable=unused-argument
        """Tool formatting - not implemented yet"""
        raise NotImplementedError(
            "Letta tool formatting is not yet implemented. "
            "This provider currently only supports model fetching."
        )

    def letta_format_messages(self, messages, system_prompt=None):  # pylint: disable=unused-argument
        """Message formatting - not implemented yet"""
        raise NotImplementedError(
            "Letta message formatting is not yet implemented. "
            "This provider currently only supports model fetching."
        )
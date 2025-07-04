import logging
import os

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import fal_client
except ImportError:
    _logger.warning(
        "Could not import fal_client. Install the package with pip: pip install fal_client"
    )
    fal_client = None


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    @api.model
    def _get_available_services(self):
        services = super()._get_available_services()
        services.append(("fal_ai", "Fal.ai"))
        return services

    def fal_ai_get_client(self):
        """Initializes and returns the fal.ai client."""
        if not fal_client:
            raise UserError(
                _(
                    "The fal_client package is not installed. Install it with pip: pip install fal_client"
                )
            )

        # fal.ai uses environment variables for the API_KEY, but we can also set it programmatically
        os.environ.setdefault("FAL_KEY", self.api_key)
        return fal_client

    def fal_ai_chat(self, messages, model=None, stream=False, **kwargs):
        """FAL AI doesn't support chat directly"""
        raise UserError(_("FAL AI provider does not support chat functionality"))

    def fal_ai_embedding(self, texts, model=None):
        """FAL AI doesn't support embeddings directly"""
        raise UserError(_("FAL AI provider does not support embedding functionality"))

    def fal_ai_generate(self, input_data, model=None, stream=False, **kwargs):
        """Generate content using FAL AI - unified generate endpoint"""
        self.ensure_one()
        client = self.fal_ai_get_client()

        # Get the model name
        model_name = model.name if model else None
        if not model_name:
            raise ValueError("Model name is required")

        try:
            if stream:
                return self._fal_ai_generate_stream(client, model_name, input_data)
            else:
                return self._fal_ai_generate_sync(client, model_name, input_data)
        except Exception as e:
            _logger.error(f"Error in FAL AI generate: {e}")
            raise UserError(_(f"FAL AI generation failed: {str(e)}"))

    def _fal_ai_generate_sync(self, client, model_name, input_data):
        """Generate content synchronously"""
        result = client.run(model_name, arguments=input_data)
        urls = self._fal_ai_extract_urls_from_result(result)
        yield {"content": urls}

    def _fal_ai_generate_stream(self, client, model_name, input_data):
        """Stream generation results"""
        try:
            stream = client.stream(model_name, arguments=input_data)
            for event in stream:
                if hasattr(event, 'data'):
                    urls = self._fal_ai_extract_urls_from_result(event.data)
                    yield {"content": urls}
                else:
                    yield {"content": event}
        except Exception as e:
            _logger.error(f"Error in FAL AI stream: {e}")
            raise UserError(_(f"FAL AI streaming failed: {str(e)}"))

    def fal_ai_models(self, model_id=None):
        """Retrieves the list of available models on fal.ai."""
        # Currently, fal.ai does not provide an endpoint to list models
        # Hardcoded known models with details including schemas
        models = [
            {
                "id": "fal-ai/flux/dev",
                "name": "fal-ai/flux/dev",
                "description": "FLUX.1 [dev] - High-quality image generation model",
                "capabilities": ["image_generation"],
                "details": {
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Description of the image to generate",
                                "title": "Prompt",
                            },
                            "negative_prompt": {
                                "type": "string",
                                "description": "Elements to avoid in the generated image",
                                "title": "Negative Prompt",
                                "default": "",
                            },
                            "image_size": {
                                "type": "string",
                                "description": "Size of the generated image",
                                "enum": [
                                    "square",
                                    "portrait",
                                    "landscape",
                                    "landscape_16_9",
                                    "landscape_4_3",
                                ],
                                "default": "square",
                                "title": "Image Size",
                            },
                            "num_images": {
                                "type": "integer",
                                "description": "Number of images to generate",
                                "minimum": 1,
                                "maximum": 4,
                                "default": 1,
                                "title": "Image Quantity",
                            },
                            "seed": {
                                "type": "integer",
                                "description": "Seed for reproducibility",
                                "default": 42,
                                "title": "Seed",
                            },
                        },
                        "required": ["prompt"],
                    },
                    "output_schema": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                        "title": "Generated Images",
                    },
                },
            },
            {
                "id": "fal-ai/lcm",
                "name": "fal-ai/lcm",
                "description": "Latent Consistency Model - Fast image generation",
                "capabilities": ["image_generation"],
                "details": {
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Description of the image to generate",
                                "title": "Prompt",
                            },
                            "negative_prompt": {
                                "type": "string",
                                "description": "Elements to avoid in the generated image",
                                "title": "Negative Prompt",
                                "default": "",
                            },
                            "image_size": {
                                "type": "string",
                                "description": "Size of the generated image",
                                "enum": ["square", "portrait", "landscape"],
                                "default": "square",
                                "title": "Image Size",
                            },
                            "num_inference_steps": {
                                "type": "integer",
                                "description": "Number of inference steps",
                                "minimum": 1,
                                "maximum": 8,
                                "default": 4,
                                "title": "Inference Steps",
                            },
                        },
                        "required": ["prompt"],
                    },
                    "output_schema": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                        "title": "Generated Images",
                    },
                },
            },
        ]

        return models

    def fal_ai_format_generation_response(self, raw_response, output_schema):
        """Format the raw generation response according to the output processing config

        Args:
            raw_response: The raw response from the provider (e.g., fal_ai client.run()).
                          Typically a list of URLs or a single URL string for images.
            output_schema (dict): Schema of the output.

        Returns:
            list: A list of strings (e.g., URLs) extracted from the raw_response.
                  Returns an empty list if no suitable strings are found or
                  if the raw_response format is unexpected.
        """
        extracted_strings = []

        if isinstance(raw_response, list):
            for item in raw_response:
                if isinstance(item, str):
                    extracted_strings.append(item)
                else:
                    _logger.warning(
                        f"FAL AI: Item in raw_response list is not a string: {item} (type: {type(item)}). Output schema: {output_schema}"
                    )
        elif isinstance(raw_response, str):
            extracted_strings.append(raw_response)
        elif raw_response is None:
            _logger.info(
                f"FAL AI: Raw response is None for schema {output_schema}. Returning empty list."
            )
        else:
            _logger.warning(
                f"FAL AI: Unexpected raw_response type: {type(raw_response)}. Full response: {raw_response}. Output schema: {output_schema}"
            )

        _logger.info(f"FAL AI: Extracted strings: {extracted_strings}")
        return extracted_strings

    def _fal_ai_extract_urls_from_result(self, result):
        """Extract URLs from fal_ai result, handling FileOutput objects and other formats"""
        urls = []

        if result is None:
            return urls

        # Example of fal_ai result: 
        # {'has_nsfw_concepts': [False], 'images': [{'content_type': 'image/png', 'height': 768, 'url': 'https://v3.fal.media/files/zebra/3Sa_l4tFKlX4-bai5Z0ST.png', 'width': 1024}], 'prompt': 'a blue cat', 'seed': 6252023, 'timings': {'inference': 2.1407407799270004}}
        if isinstance(result, list):
            # If result is a list, extract URLs from each item
            for item in result:
                url = self._fal_ai_extract_single_url(item)
                if url:
                    urls.append(url)

        elif isinstance(result, dict):
            # If result is a dictionary, check for 'images' key or other URL fields
            if "images" in result:
                for item in result["images"]:
                    url = self._fal_ai_extract_single_url(item)
                    if url:
                        urls.append(url)
            else:
                # Check for other potential URL fields in the dictionary
                url = self._fal_ai_extract_single_url(result)
                if url:
                    urls.append(url)

        else:
            # If result is a single item (not a list or dict), extract URL directly
            url = self._fal_ai_extract_single_url(result)
            if url:
                urls.append(url)

        return urls

    def _fal_ai_extract_single_url(self, item):
        """Extract URL from a single result item"""
        if isinstance(item, dict):
            if "url" in item:
                return item["url"]
            elif "content" in item and isinstance(item["content"], str):
                return item["content"]
        elif isinstance(item, str):
            return item
        return None

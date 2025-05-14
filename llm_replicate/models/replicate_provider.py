import json
import logging

import jsonref
import replicate

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    @api.model
    def _get_available_services(self):
        services = super()._get_available_services()
        return services + [("replicate", "Replicate")]

    def replicate_get_client(self):
        """Get Replicate client instance"""
        return replicate.Client(api_token=self.api_key)

    def replicate_chat(self, messages, model=None, stream=False, **kwargs):
        """Send chat messages using Replicate"""
        model = self.get_model(model, "chat")

        # Format messages for Replicate
        # Most Replicate models expect a simple prompt string
        prompt = "\n".join(f"{msg['role']}: {msg['content']}" for msg in messages)

        response = self.client.run(model.name, input={"prompt": prompt})

        if not stream:
            # Replicate responses can vary by model, handle common formats
            content = (
                "".join(response)
                if isinstance(response, list) or isinstance(response, tuple)
                else str(response)
            )
            yield {"role": "assistant", "content": content}
        else:
            for chunk in response:
                yield {"role": "assistant", "content": str(chunk)}

    def replicate_embedding(self, texts, model=None):
        """Generate embeddings using Replicate"""
        model = self.get_model(model, "embedding")

        if not isinstance(texts, list):
            texts = [texts]

        response = self.client.run(model.name, input={"sentences": texts})

        # Ensure we return a list of embeddings
        if len(texts) == 1:
            return [response] if not isinstance(response, list) else response
        return response

    def replicate_models(self, model_id=None):
        self.ensure_one()
        """List available Replicate models with pagination support"""

        # If a specific model ID is requested, fetch just that model
        if model_id:
            model = self.client.models.get(model_id)
            yield self._replicate_parse_model(model)
        else:
            # If no specific model requested, fetch all models with pagination
            cursor = ...

            while cursor:
                # Get page of results
                page = self.client.models.list(cursor=cursor)

                # Process models in current page
                for model in page.results:
                    yield self._replicate_parse_model(model)

                cursor = page.next
                if cursor is None:
                    break

    def _replicate_parse_model(self, model):
        details = self.serialize_model_data(model.dict())
        capabilities = []
        if "chat" in model.id.lower() or "llm" in model.id.lower():
            capabilities.append("chat")
        if "embedding" in model.id.lower():
            capabilities.append("embedding")
        if any(kw in model.id.lower() for kw in ["vision", "image", "multimodal"]):
            capabilities.append("multimodal")
        return {
            "id": model.id,
            "name": model.id,
            "details": details,
            "capabilities": capabilities,
        }

    def replicate_generate_io_schema(self, model_record):
        """Generate a configuration from Replicate model details

        Args:
            model_record (llm.model): The model record to generate config for
        """
        self.ensure_one()

        # Get model details
        details = model_record.details or {}
        model_name = model_record.name

        # Extract OpenAPI schema from details
        openapi_schema = None
        if details.get("latest_version", {}).get("openapi_schema"):
            openapi_schema = details["latest_version"]["openapi_schema"]

        # Extract and process input schema
        input_schema = {}
        output_schema = {}
        if openapi_schema:
            resolved_openapi_schema = jsonref.replace_refs(openapi_schema)
            input_schema = resolved_openapi_schema["components"]["schemas"]["Input"]
            output_schema = resolved_openapi_schema["components"]["schemas"]["Output"]

            # Enforce additionalProperties: false to validate against unknown fields
            input_schema["additionalProperties"] = False
            output_schema["additionalProperties"] = False
        else:
            _logger.warning(f"No OpenAPI schema found for model {model_name}")

        model_record.write(
            {
                "input_schema": json.dumps(input_schema, indent=2)
                if input_schema
                else None,
                "output_schema": json.dumps(output_schema, indent=2)
                if output_schema
                else None,
            }
        )

    def replicate_generate_media(self, inputs, model_record=None, stream=False):
        """Generate media content using this provider"""
        _logger.info(
            f"Generating media content using {model_record.name} with inputs {inputs}"
        )
        # Get full model name including version if specified
        model_name = model_record._replicate_model_name_with_version()
        if not model_name:
            model_name = model_record.name

        if not model_name:
            raise ValueError("Model name is required")

        # TODO: Might need to use prediction_create method, to have streaming and more details about prediction
        result = self.client.run(model_name, input=inputs)

        # Extract URLs from FileOutput objects
        urls = []
        if isinstance(result, list):
            for item in result:
                if hasattr(item, "url"):
                    urls.append(item.url)
                else:
                    urls.append(str(item))
        else:
            if hasattr(result, "url"):
                urls.append(result.url)
            else:
                urls.append(str(result))

        # TODO: Need to properly check how to detect if some model has streaming/or not
        if stream:
            yield {"content": urls}
        else:
            return urls

    def replicate_format_generation_response(self, raw_response, output_schema):
        """Format the raw generation response according to the output processing config

        Args:
            raw_response: The raw response from the provider (e.g., Replicate client.run()).
                          Typically a list of URLs or a single URL string for images.
            output_schema (dict): Schema of the output.

        Returns:
            list: A list of strings (e.g., URLs) extracted from the raw_response.
                  Returns an empty list if no suitable strings are found or
                  if the raw_response format is unexpected.
        """
        _logger.debug(
            f"Formatting Replicate raw_response: {raw_response} with schema: {output_schema}"
        )

        extracted_strings = []

        # output_schema example: {"type": "array", "items": {"type": "string", "format": "uri"}}
        # This implies the raw_response should ideally be a list of strings, or a single string.

        if isinstance(raw_response, list):
            for item in raw_response:
                if isinstance(item, str):
                    extracted_strings.append(item)
                else:
                    # Log if an item in the list is not a string, but continue processing
                    _logger.warning(
                        f"Replicate: Item in raw_response list is not a string: {item} (type: {type(item)}). Output schema: {output_schema}"
                    )
        elif isinstance(raw_response, str):
            # If the raw_response is a single string, assume it's the URL/data itself.
            extracted_strings.append(raw_response)
        elif raw_response is None:
            _logger.info(
                f"Replicate: Raw response is None for schema {output_schema}. Returning empty list."
            )
        else:
            _logger.warning(
                f"Replicate: Unexpected raw_response type: {type(raw_response)}. Full response: {raw_response}. Output schema: {output_schema}"
            )
            # For now, we return an empty list. More sophisticated parsing based on
            # output_schema could be added here if needed for complex objects.

        _logger.info(
            f"Replicate: Extracted strings: {extracted_strings} for schema {output_schema}"
        )
        return extracted_strings

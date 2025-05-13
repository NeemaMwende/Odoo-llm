import json
import logging

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

    def _extract_schema_by_name(self, openapi_schema, schema_name):
        """Extract a schema by name from the components section

        Args:
            openapi_schema (dict): The OpenAPI schema dictionary
            schema_name (str): The name of the schema to extract (e.g., 'Input', 'Output')

        Returns:
            dict: The extracted schema or empty dict if not found
        """
        if (
            not openapi_schema
            or "components" not in openapi_schema
            or "schemas" not in openapi_schema["components"]
        ):
            return {}

        # Check if the schema exists directly
        schemas = openapi_schema["components"]["schemas"]
        if schema_name in schemas:
            schema = schemas[schema_name]

            # Resolve any references in the schema
            if "$ref" in schema:
                schema = self._resolve_schema_reference(openapi_schema, schema["$ref"])

            return schema

        # If not found directly, look for it in PredictionRequest/Response
        if schema_name == "Input" and "PredictionRequest" in schemas:
            pred_request = schemas["PredictionRequest"]
            if "properties" in pred_request and "input" in pred_request["properties"]:
                input_prop = pred_request["properties"]["input"]
                if "$ref" in input_prop:
                    return self._resolve_schema_reference(
                        openapi_schema, input_prop["$ref"]
                    )
                return input_prop

        elif schema_name == "Output" and "PredictionResponse" in schemas:
            pred_response = schemas["PredictionResponse"]
            if (
                "properties" in pred_response
                and "output" in pred_response["properties"]
            ):
                output_prop = pred_response["properties"]["output"]
                if "$ref" in output_prop:
                    return self._resolve_schema_reference(
                        openapi_schema, output_prop["$ref"]
                    )
                return output_prop

        return {}

    def _resolve_schema_reference(self, openapi_schema, ref):
        """Resolve a schema reference to its actual schema

        Args:
            openapi_schema (dict): The OpenAPI schema dictionary
            ref (str): The reference string (e.g., '#/components/schemas/PredictionResponse')

        Returns:
            dict: The resolved schema or empty dict if not found
        """
        if not ref.startswith("#/"):
            return {}

        ref_parts = ref.split("/")[1:]  # Remove the '#' part

        # Navigate through the schema to find the referenced object
        current = openapi_schema
        for part in ref_parts:
            if part not in current:
                return {}
            current = current[part]

        return current

    def _process_input_schema(self, schema, openapi_schema):
        """Process and flatten an input schema for dynamic form rendering

        Args:
            schema (dict): The schema to process
            openapi_schema (dict): The full OpenAPI schema for reference resolution

        Returns:
            dict: A flattened schema with fields in a consistent format
        """
        # If schema has a reference, resolve it
        if "$ref" in schema:
            schema = self._resolve_schema_reference(openapi_schema, schema["$ref"])

        # Get properties and required fields
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Transform to flattened format
        fields = []
        for name, prop in properties.items():
            # Resolve property reference if needed
            if "$ref" in prop:
                prop = self._resolve_schema_reference(openapi_schema, prop["$ref"])

            # Basic field properties
            field = {
                "name": name,
                "label": prop.get("title", name),
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
                "required": name in required_fields,
                "order": prop.get("x-order", 999),
            }

            # Handle default value
            if "default" in prop:
                field["default"] = prop["default"]

            # Handle type-specific properties
            if field["type"] in ["integer", "number"]:
                if "minimum" in prop:
                    field["minimum"] = prop["minimum"]
                if "maximum" in prop:
                    field["maximum"] = prop["maximum"]

            # Handle enums directly in the property
            if "enum" in prop:
                field["type"] = "enum"
                field["options"] = [{"value": v, "label": str(v)} for v in prop["enum"]]

            # Handle enums via allOf with $ref
            if "allOf" in prop:
                for item in prop.get("allOf", []):
                    if "$ref" in item:
                        # Extract the enum name from the reference
                        enum_schema = self._resolve_schema_reference(
                            openapi_schema, item["$ref"]
                        )
                        if "enum" in enum_schema:
                            field["type"] = "enum"
                            field["options"] = [
                                {"value": v, "label": str(v)}
                                for v in enum_schema["enum"]
                            ]

            # Handle formats for strings
            if field["type"] == "string" and "format" in prop:
                field["format"] = prop["format"]

            fields.append(field)

        # Sort by order
        fields.sort(key=lambda x: x.get("order", 999))

        return {
            "title": schema.get("title", "Model Input Parameters"),
            "description": schema.get(
                "description", "Parameters for generating content with this model"
            ),
            "fields": fields,
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

        # Log the details for debugging
        _logger.info(f"Model details for {model_name}: {details}")

        # Extract OpenAPI schema from details
        openapi_schema = None
        if details.get("latest_version", {}).get("openapi_schema"):
            openapi_schema = details["latest_version"]["openapi_schema"]

        # Extract and process input schema
        input_schema = {}
        if openapi_schema:
            # Extract the Input schema
            raw_input_schema = self._extract_schema_by_name(openapi_schema, "Input")

            if raw_input_schema:
                # Process the input schema for form rendering
                input_schema = self._process_input_schema(
                    raw_input_schema, openapi_schema
                )
                _logger.info(f"Extracted and processed Input schema: {input_schema}")
            else:
                _logger.warning(f"Could not find Input schema for model {model_name}")
                # Create a minimal schema
                input_schema = {
                    "title": "Model Input Parameters",
                    "description": "Parameters for generating content with this model",
                    "fields": [],
                }
        else:
            _logger.warning(f"No OpenAPI schema found for model {model_name}")

        # Extract output schema
        output_schema = {}
        if openapi_schema:
            # Extract the Output schema
            output_schema = self._extract_schema_by_name(openapi_schema, "Output")

            if output_schema:
                _logger.info(f"Extracted Output schema: {output_schema}")
            else:
                _logger.warning(f"Could not find Output schema for model {model_name}")
                # Create a minimal schema
                output_schema = {
                    "type": "object",
                    "title": "Output",
                    "description": "Model output",
                }
        _logger.info(f"Input schema: {input_schema}")
        _logger.info(f"Output schema: {output_schema}")

        model_record.write(
            {
                "input_schema": json.dumps(input_schema) if input_schema else None,
                "output_schema": json.dumps(output_schema) if output_schema else None,
            }
        )

    def replicate_generate_media(self, inputs, model_record=None, stream=False):
        """Generate media content using this provider"""
        _logger.info(
            f"Generating media content using {model_record.name} with inputs {inputs}"
        )

        result = self.client.run(model_record.name, input=inputs)

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

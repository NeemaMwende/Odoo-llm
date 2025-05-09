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
        if not openapi_schema or 'components' not in openapi_schema or 'schemas' not in openapi_schema['components']:
            return {}
            
        # Check if the schema exists directly
        schemas = openapi_schema['components']['schemas']
        if schema_name in schemas:
            schema = schemas[schema_name]
            
            # Resolve any references in the schema
            if '$ref' in schema:
                schema = self._resolve_schema_reference(openapi_schema, schema['$ref'])
                
            return schema
            
        # If not found directly, look for it in PredictionRequest/Response
        if schema_name == 'Input' and 'PredictionRequest' in schemas:
            pred_request = schemas['PredictionRequest']
            if 'properties' in pred_request and 'input' in pred_request['properties']:
                input_prop = pred_request['properties']['input']
                if '$ref' in input_prop:
                    return self._resolve_schema_reference(openapi_schema, input_prop['$ref'])
                return input_prop
                
        elif schema_name == 'Output' and 'PredictionResponse' in schemas:
            pred_response = schemas['PredictionResponse']
            if 'properties' in pred_response and 'output' in pred_response['properties']:
                output_prop = pred_response['properties']['output']
                if '$ref' in output_prop:
                    return self._resolve_schema_reference(openapi_schema, output_prop['$ref'])
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
        if not ref.startswith('#/'):
            return {}
            
        ref_parts = ref.split('/')[1:]  # Remove the '#' part
        
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
        if '$ref' in schema:
            schema = self._resolve_schema_reference(openapi_schema, schema['$ref'])
        
        # Get properties and required fields
        properties = schema.get('properties', {})
        required_fields = schema.get('required', [])
        
        # Transform to flattened format
        fields = []
        for name, prop in properties.items():
            # Resolve property reference if needed
            if '$ref' in prop:
                prop = self._resolve_schema_reference(openapi_schema, prop['$ref'])
            
            # Basic field properties
            field = {
                'name': name,
                'label': prop.get('title', name),
                'type': prop.get('type', 'string'),
                'description': prop.get('description', ''),
                'required': name in required_fields,
                'order': prop.get('x-order', 999)
            }
            
            # Handle default value
            if 'default' in prop:
                field['default'] = prop['default']
            
            # Handle type-specific properties
            if field['type'] in ['integer', 'number']:
                if 'minimum' in prop:
                    field['minimum'] = prop['minimum']
                if 'maximum' in prop:
                    field['maximum'] = prop['maximum']
            
            # Handle enums directly in the property
            if 'enum' in prop:
                field['type'] = 'enum'
                field['options'] = [{'value': v, 'label': str(v)} for v in prop['enum']]
            
            # Handle enums via allOf with $ref
            if 'allOf' in prop:
                for item in prop.get('allOf', []):
                    if '$ref' in item:
                        # Extract the enum name from the reference
                        enum_schema = self._resolve_schema_reference(openapi_schema, item['$ref'])
                        if 'enum' in enum_schema:
                            field['type'] = 'enum'
                            field['options'] = [{'value': v, 'label': str(v)} for v in enum_schema['enum']]
            
            # Handle formats for strings
            if field['type'] == 'string' and 'format' in prop:
                field['format'] = prop['format']
            
            fields.append(field)
        
        # Sort by order
        fields.sort(key=lambda x: x.get('order', 999))
        
        return {
            'title': schema.get('title', 'Model Input Parameters'),
            'description': schema.get('description', 'Parameters for generating content with this model'),
            'fields': fields
        }
        
    def _extract_flattened_schema(self, schema_dict):
        """Extract and flatten an OpenAPI schema into a format suitable for dynamic forms
        
        Args:
            schema_dict (dict): The OpenAPI schema dictionary
            
        Returns:
            dict: A flattened schema with fields in a consistent format
        """
        # Try to find the Input schema in components
        components = schema_dict.get('components', {})
        schemas = components.get('schemas', {})
        input_schema = schemas.get('Input', {})
        
        if not input_schema:
            _logger.warning("Could not find Input schema in OpenAPI components")
            return {
                'title': 'Model Input Parameters',
                'description': 'Parameters for generating content with this model',
                'fields': []
            }
        
        # Get properties and required fields
        properties = input_schema.get('properties', {})
        required_fields = input_schema.get('required', [])
        
        # Transform to flattened format
        fields = []
        for name, prop in properties.items():
            # Basic field properties
            field = {
                'name': name,
                'label': prop.get('title', name),
                'type': prop.get('type', 'string'),
                'description': prop.get('description', ''),
                'required': name in required_fields,
                'order': prop.get('x-order', 999)
            }
            
            # Handle default value
            if 'default' in prop:
                field['default'] = prop['default']
            
            # Handle type-specific properties
            if field['type'] in ['integer', 'number']:
                if 'minimum' in prop:
                    field['minimum'] = prop['minimum']
                if 'maximum' in prop:
                    field['maximum'] = prop['maximum']
            
            # Handle enums directly in the property
            if 'enum' in prop:
                field['type'] = 'enum'
                field['options'] = [{'value': v, 'label': str(v)} for v in prop['enum']]
            
            # Handle enums via allOf with $ref
            if 'allOf' in prop:
                for item in prop.get('allOf', []):
                    if '$ref' in item:
                        # Extract the enum name from the reference
                        ref_parts = item['$ref'].split('/')
                        if len(ref_parts) > 0:
                            enum_name = ref_parts[-1]
                            enum_schema = schemas.get(enum_name, {})
                            if 'enum' in enum_schema:
                                field['type'] = 'enum'
                                field['options'] = [{'value': v, 'label': str(v)} for v in enum_schema['enum']]
            
            # Handle formats for strings
            if field['type'] == 'string' and 'format' in prop:
                field['format'] = prop['format']
            
            fields.append(field)
        
        # Sort by order
        fields.sort(key=lambda x: x.get('order', 999))
        
        return {
            'title': input_schema.get('title', 'Model Input Parameters'),
            'description': input_schema.get('description', 'Parameters for generating content with this model'),
            'fields': fields
        }
    
    def replicate_get_config_from_raw_schema(self, model_record):
        """Generate a configuration from Replicate model details
        
        Args:
            raw_schema_components (dict): Raw schema components from the provider
            model_record (llm.model): The model record to generate config for
            
        Returns:
            llm.generation.config record created from the schema
        """
        self.ensure_one()
        
        # Get model details
        details = model_record.details or {}
        model_name = model_record.name
        
        # Log the details for debugging
        _logger.info(f"Model details for {model_name}: {details}")
        
        # Extract OpenAPI schema from details
        openapi_schema = None
        if details.get('latest_version', {}).get('openapi_schema'):
            openapi_schema = details['latest_version']['openapi_schema']
        
        # Extract and process input schema
        input_schema = {}
        if openapi_schema:
            # Extract the Input schema
            raw_input_schema = self._extract_schema_by_name(openapi_schema, 'Input')
            
            if raw_input_schema:
                # Process the input schema for form rendering
                input_schema = self._process_input_schema(raw_input_schema, openapi_schema)
                _logger.info(f"Extracted and processed Input schema: {input_schema}")
            else:
                _logger.warning(f"Could not find Input schema for model {model_name}")
                # Create a minimal schema
                input_schema = {
                    'title': 'Model Input Parameters',
                    'description': 'Parameters for generating content with this model',
                    'fields': []
                }
        else:
            _logger.warning(f"No OpenAPI schema found for model {model_name}")
        
        # Extract output schema
        output_schema = {}
        if openapi_schema:
            # Extract the Output schema
            output_schema = self._extract_schema_by_name(openapi_schema, 'Output')
            
            if output_schema:
                _logger.info(f"Extracted Output schema: {output_schema}")
            else:
                _logger.warning(f"Could not find Output schema for model {model_name}")
                # Create a minimal schema
                output_schema = {
                    'type': 'object',
                    'title': 'Output',
                    'description': 'Model output'
                }
        _logger.info(f"Input schema: {input_schema}")
        _logger.info(f"Output schema: {output_schema}")
        
        # Check if the model already has a generation config
        if model_record.generation_config_id:
            # Update the existing config
            model_record.generation_config_id.write({
                'input_schema': input_schema,
                'output_schema_raw': output_schema,
                'description': f"Updated configuration for {model_name}"
            })
            generation_config = model_record.generation_config_id
            _logger.info(f"Updated existing generation config for {model_name}")
        else:
            # Create a new generation config
            generation_config = self.env['llm.generation.config'].create({
                'name': f"{model_name} Generation Config",
                'model_id': model_record.id,
                'description': f"Generated configuration for {model_name}",
                'input_schema': input_schema,
                'output_schema_raw': output_schema
            })
            
            # Link the config back to the model
            model_record.write({'generation_config_id': generation_config.id})
            _logger.info(f"Created new generation config for {model_name}")
        
        return generation_config

    def replicate_generate_media(self, inputs, model_record=None):
        """Generate media content using this provider"""
        _logger.info(f"Generating media content using {model_record.name} with inputs {inputs}")

        result = self.client.run(
            model_record.name,
            input=inputs
        )

        _logger.info(f"Generated media content using {model_record.name} with inputs {inputs}")
        _logger.info(f"Generated media content result: {result}")

        return result
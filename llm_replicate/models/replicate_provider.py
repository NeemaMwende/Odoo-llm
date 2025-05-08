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
        
    def _extract_endpoint_schema(self, openapi_schema, path, method, response_code='200', request_or_response='response'):
        """Extract schema from a specific endpoint path and method
        
        Args:
            openapi_schema (dict): The OpenAPI schema dictionary
            path (str): The endpoint path (e.g., '/predictions')
            method (str): The HTTP method (e.g., 'post', 'get')
            response_code (str): The response code to extract (default: '200')
            request_or_response (str): Whether to extract request or response schema (default: 'response')
            
        Returns:
            dict: The extracted schema or empty dict if not found
        """
        if not openapi_schema or 'paths' not in openapi_schema or path not in openapi_schema['paths']:
            return {}
            
        endpoint = openapi_schema['paths'][path]
        if method not in endpoint:
            return {}
            
        method_data = endpoint[method]
        
        # Extract request schema
        if request_or_response == 'request':
            if 'requestBody' not in method_data:
                return {}
                
            request_body = method_data['requestBody']
            if 'content' not in request_body or 'application/json' not in request_body['content']:
                return {}
                
            content = request_body['content']['application/json']
            if 'schema' not in content:
                return {}
                
            schema = content['schema']
            
        # Extract response schema
        else:  # response
            if 'responses' not in method_data or response_code not in method_data['responses']:
                return {}
                
            response = method_data['responses'][response_code]
            if 'content' not in response or 'application/json' not in response['content']:
                return {}
                
            content = response['content']['application/json']
            if 'schema' not in content:
                return {}
                
            schema = content['schema']
        
        # Resolve schema reference if needed
        if '$ref' in schema:
            schema = self._resolve_schema_reference(openapi_schema, schema['$ref'])
            
        return schema
    
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
    
    def replicate_get_config_from_raw_schema(self, raw_schema_components, model_record):
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
        if raw_schema_components:
            openapi_schema = raw_schema_components
        elif details.get('latest_version', {}).get('openapi_schema'):
            openapi_schema = details['latest_version']['openapi_schema']
        
        # Extract and flatten the schema for input
        input_schema = {}
        if openapi_schema:
            # First check the /predictions POST endpoint request body
            prediction_request_schema = self._extract_endpoint_schema(
                openapi_schema, 
                '/predictions', 
                'post', 
                request_or_response='request'
            )
            
            if prediction_request_schema:
                # Flatten the request schema for form rendering
                input_schema = self._process_input_schema(prediction_request_schema, openapi_schema)
                _logger.info(f"Extracted input schema from /predictions endpoint: {input_schema}")
            else:
                # Fallback to the old method
                input_schema = self._extract_flattened_schema(openapi_schema)
                _logger.info(f"Extracted input schema from components: {input_schema}")
        else:
            _logger.warning(f"No OpenAPI schema found for model {model_name}")
        
        # Extract output schema from prediction endpoints
        output_schema = {}
        if openapi_schema:
            # First check the /predictions POST endpoint response
            prediction_response_schema = self._extract_endpoint_schema(
                openapi_schema, 
                '/predictions', 
                'post', 
                response_code='200', 
                request_or_response='response'
            )
            
            # If we got a response schema, look for the output field
            if prediction_response_schema and 'properties' in prediction_response_schema:
                if 'output' in prediction_response_schema['properties']:
                    output_schema = prediction_response_schema['properties']['output']
                    # Resolve any references in the output schema
                    if output_schema and '$ref' in output_schema:
                        output_schema = self._resolve_schema_reference(openapi_schema, output_schema['$ref'])
                    _logger.info(f"Found output schema from /predictions endpoint: {output_schema}")
            
            # Fallback: If we couldn't find it in the endpoint, look in components
            if not output_schema and 'components' in openapi_schema and 'schemas' in openapi_schema['components']:
                # Try to find the Output schema
                if 'Output' in openapi_schema['components']['schemas']:
                    output_schema = openapi_schema['components']['schemas']['Output']
                    # Resolve any references in the output schema
                    if output_schema and '$ref' in output_schema:
                        output_schema = self._resolve_schema_reference(openapi_schema, output_schema['$ref'])
                    _logger.info(f"Found Output schema in components: {output_schema}")
                # If not found, look for PredictionResponse
                elif 'PredictionResponse' in openapi_schema['components']['schemas']:
                    pred_response = openapi_schema['components']['schemas']['PredictionResponse']
                    if 'properties' in pred_response and 'output' in pred_response['properties']:
                        output_schema = pred_response['properties']['output']
                        # Resolve any references in the output schema
                        if output_schema and '$ref' in output_schema:
                            output_schema = self._resolve_schema_reference(openapi_schema, output_schema['$ref'])
                        _logger.info(f"Found output in PredictionResponse schema: {output_schema}")
        _logger.info(f"Input schema: {input_schema}")
        _logger.info(f"Output schema: {output_schema}")
        return True
        # # Create a generation config
        # generation_config = self.env['llm.generation.config'].create({
        #     'name': f"{model_name} Generation Config",
        #     'model_id': model_record.id,
        #     'description': f"Generated configuration for {model_name}",
        #     'input_schema': input_schema,
        #     'output_schema_raw': output_schema
        # })
        
        # # Link the config back to the model
        # model_record.write({'generation_config_id': generation_config.id})
        
        # return generation_config

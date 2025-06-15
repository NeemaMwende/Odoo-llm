# Add this to your existing controller or create controllers/main.py

import json
import logging
from odoo import http
from odoo.http import request
from odoo.addons.llm_thread.llm_thread.main import LLMThreadController

_logger = logging.getLogger(__name__)


class LLMGenerateController(LLMThreadController):

    @http.route('/llm/thread/generate-media', type='http', auth="user", csrf=False)
    def generate_media(self, thread_id, message, generation_inputs, **kwargs):
        """Handle media generation requests with streaming response."""

        try:
            thread_id = int(thread_id)
            thread = request.env['llm.thread'].browse(thread_id)

            if not thread.exists():
                return self._error_response("Thread not found")

            if not thread.model_id._is_media_generation_model():
                return self._error_response("Thread model is not configured for media generation")

            # Parse generation inputs
            try:
                inputs_dict = json.loads(generation_inputs)
            except json.JSONDecodeError as e:
                return self._error_response(f"Invalid JSON in generation_inputs: {e}")

            # Check if prompt template rendering should be skipped
            without_template = inputs_dict.pop('_skipPromptTemplate', False)

            # Combine generation inputs with rendered prompt template if needed
            if not without_template:
                final_inputs = request.env['llm.thread'].render_generation_json(
                    thread_id, inputs_dict, without_prompt_template=False
                )
            else:
                final_inputs = inputs_dict

            # Validate inputs against model schema
            validation_result = self._validate_generation_inputs(thread.model_id, final_inputs)
            if not validation_result['valid']:
                return self._error_response(f"Input validation failed: {validation_result['error']}")

            # Create user message with generation inputs
            user_message = thread._post_message(
                subtype_xmlid='llm_mail_message_subtypes.mt_llm_user',
                body=message,
                generation_inputs=json.dumps(final_inputs),  # Store the final combined inputs
                author_id=request.env.user.partner_id.id,
            )

            # Generate streaming response
            return self._stream_response(self._generate_media_stream(thread, user_message))

        except Exception as e:
            _logger.exception("Error in generate_media endpoint")
            return self._error_response(f"Internal server error: {str(e)}")

    def _validate_generation_inputs(self, model, inputs):
        """Validate generation inputs against model schema."""
        try:
            if not model.input_schema:
                return {'valid': True}  # No schema to validate against

            # Parse schema if it's a string
            schema = model.input_schema
            if isinstance(schema, str):
                schema = json.loads(schema)

            # Basic validation - you might want to use jsonschema library for full validation
            if 'properties' in schema:
                required_fields = schema.get('required', [])

                # Check required fields
                for field in required_fields:
                    if field not in inputs or inputs[field] is None or inputs[field] == '':
                        return {'valid': False, 'error': f"Required field '{field}' is missing or empty"}

                # Check field types (basic validation)
                for field_name, field_value in inputs.items():
                    if field_name in schema['properties']:
                        field_def = schema['properties'][field_name]
                        expected_type = field_def.get('type')

                        if expected_type == 'integer' and not isinstance(field_value, int):
                            try:
                                inputs[field_name] = int(field_value)
                            except (ValueError, TypeError):
                                return {'valid': False, 'error': f"Field '{field_name}' must be an integer"}

                        elif expected_type == 'number' and not isinstance(field_value, (int, float)):
                            try:
                                inputs[field_name] = float(field_value)
                            except (ValueError, TypeError):
                                return {'valid': False, 'error': f"Field '{field_name}' must be a number"}

                        elif expected_type == 'boolean' and not isinstance(field_value, bool):
                            if isinstance(field_value, str):
                                inputs[field_name] = field_value.lower() in ('true', '1', 'yes')
                            else:
                                inputs[field_name] = bool(field_value)

            return {'valid': True}

        except Exception as e:
            _logger.error(f"Error validating inputs: {e}")
            return {'valid': False, 'error': f"Validation error: {str(e)}"}

    def _generate_media_stream(self, thread, user_message):
        """Generate media streaming response."""
        try:
            # Use the existing _next_step method which handles media generation
            assistant_message_gen = thread._next_step(user_message)

            for event in assistant_message_gen:
                yield event

        except Exception as e:
            _logger.exception("Error in media generation stream")
            yield {
                'type': 'error',
                'error': f'Generation failed: {str(e)}'
            }

    def _error_response(self, error_message):
        """Return an error response in Server-Sent Events format."""
        def error_stream():
            yield {
                'type': 'error',
                'error': error_message
            }

        return self._stream_response(error_stream())

    def _stream_response(self, generator):
        """Convert generator to Server-Sent Events response."""
        def event_stream():
            try:
                for event in generator:
                    if isinstance(event, dict):
                        yield f"data: {json.dumps(event)}\n\n"
                    else:
                        # Handle other event types if needed
                        yield f"data: {json.dumps({'type': 'unknown', 'data': str(event)})}\n\n"

                # Send completion event
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception as e:
                _logger.exception("Error in event stream")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return request.make_response(
            event_stream(),
            headers=[
                ('Content-Type', 'text/event-stream'),
                ('Cache-Control', 'no-cache'),
                ('Connection', 'keep-alive'),
            ]
        )

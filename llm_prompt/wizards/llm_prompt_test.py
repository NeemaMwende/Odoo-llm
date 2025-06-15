import json
import logging
import yaml
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class LLMPromptTest(models.TransientModel):
    _name = "llm.prompt.test"
    _description = "LLM Prompt Test Wizard"

    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt",
        required=True,
        readonly=True,
    )

    # Context and arguments
    test_context = fields.Text(
        string="Test Context (JSON)",
        help="Context arguments to test the prompt with",
        default=lambda self: self._get_default_context(),
    )

    # Reference field for related record selection - allow all models
    related_record_ref = fields.Reference(
        selection="_get_reference_models",
        string="Related Record",
        help="Select any record to use as context for testing related_record.get_field() functions",
    )

    @api.model
    def _get_reference_models(self):
        """Get list of all available models for reference selection."""
        models = self.env['ir.model'].search([
            ('state', '!=', 'manual'),
            ('transient', '=', False),
        ], order='name')

        return [(model.model, model.name) for model in models]

    # Results
    rendered_template = fields.Text(
        string="Rendered Template",
        readonly=True,
        help="Template after argument substitution",
    )

    messages_json = fields.Text(
        string="Generated Messages (JSON)",
        readonly=True,
        help="Generated messages in JSON format",
    )

    messages_yaml = fields.Text(
        string="Generated Messages (YAML)",
        readonly=True,
        help="Generated messages in YAML format",
    )

    messages_text = fields.Text(
        string="Generated Messages (Text)",
        readonly=True,
        help="Generated messages in readable text format",
    )

    # Display options
    result_format = fields.Selection([
        ('json', 'JSON'),
        ('yaml', 'YAML'),
        ('text', 'Text'),
    ], string="Result Format", default='json')

    # Status fields
    has_error = fields.Boolean(
        string="Has Error",
        default=False,
        help="Whether there was an error during evaluation",
    )

    error_message = fields.Text(
        string="Error Message",
        readonly=True,
        help="Error message if evaluation failed",
    )

    # Additional fields for displaying prompt info
    original_template = fields.Text(
        string="Original Template",
        compute="_compute_prompt_info",
        help="Original template content from the prompt",
    )

    arguments_schema = fields.Text(
        string="Arguments Schema",
        compute="_compute_prompt_info",
        help="Arguments schema from the prompt",
    )

    @api.depends('prompt_id')
    def _compute_prompt_info(self):
        """Compute prompt information for display"""
        for wizard in self:
            if wizard.prompt_id:
                wizard.original_template = wizard.prompt_id.template or ""
                wizard.arguments_schema = wizard.prompt_id.arguments_json or "{}"
            else:
                wizard.original_template = ""
                wizard.arguments_schema = "{}"

    def _get_default_context(self):
        """Get default context using prompt's method"""
        prompt_id = self.env.context.get('default_prompt_id')
        if not prompt_id:
            return "{}"

        prompt = self.env['llm.prompt'].browse(prompt_id)
        if not prompt.exists():
            return "{}"

        # Use the prompt's method to get default context
        defaults = prompt.get_default_test_context()
        return json.dumps(defaults, indent=2) if defaults else "{}"

    def _create_test_thread(self):
        """
        Create a temporary test thread to use for testing.
        This ensures we test using the thread's get_context() method.

        Returns:
            llm.thread: Temporary test thread
        """
        return self.env['llm.thread'].create({
            'name': f'Test Thread for {self.prompt_id.name}',
            'prompt_id': self.prompt_id.id,
            'related_record': self.related_record_ref and f"{self.related_record_ref._name},{self.related_record_ref.id}" or False,
        })

    def _populate_context_from_record(self):
        """Populate context using thread's get_context method"""
        if not self.related_record_ref:
            return

        try:
            _logger.info("Auto-populating context from record: %s (ID: %s)",
                         self.related_record_ref, self.related_record_ref.id)

            # Parse existing context, preserving user data
            try:
                existing_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError:
                existing_context = {}

            # Create a temporary test thread to use its get_context method
            test_thread = self._create_test_thread()

            try:
                # Use the thread's get_context method to get the canonical context
                thread_context = test_thread.get_context()

                # Use the thread's method to generate sample context
                sample_context = test_thread.generate_sample_context_from_record()

                # Merge contexts, preserving existing user data
                for key, value in sample_context.items():
                    if key not in existing_context:  # Only add if not already present
                        existing_context[key] = value

                self.test_context = json.dumps(existing_context, indent=2)

                _logger.info("Auto-populated context with %d fields", len(sample_context))
            finally:
                # Clean up test thread
                test_thread.unlink()

        except Exception as e:
            _logger.exception("Error auto-populating context from record")

    def test_prompt_with_context(self, user_context=None):
        """
        Test the prompt with given parameters using thread's get_context method.

        Args:
            user_context (dict): Additional context from user (optional)

        Returns:
            dict: Result containing rendered_template, messages, and any errors
        """
        if not self.prompt_id:
            return {
                'success': False,
                'rendered_template': "",
                'messages': [],
                'context_used': {},
                'error': "No prompt configured"
            }

        try:
            # Create a temporary test thread
            test_thread = self._create_test_thread()

            try:
                # Get context using the thread's canonical get_context method
                context = test_thread.get_context(user_context)

                # Mark as test to avoid updating usage statistics
                context['is_test'] = True

                # Use the prompt to render and generate messages (same as production)
                rendered_template = self.prompt_id.render(context)
                messages = self.prompt_id.get_messages(context)

                return {
                    'success': True,
                    'rendered_template': rendered_template,
                    'messages': messages,
                    'context_used': context,
                    'error': None
                }
            finally:
                # Clean up test thread
                test_thread.unlink()

        except Exception as e:
            _logger.exception("Error testing prompt %s", self.prompt_id.name)
            return {
                'success': False,
                'rendered_template': "",
                'messages': [],
                'context_used': user_context or {},
                'error': str(e)
            }

    @api.onchange('related_record_ref')
    def _onchange_related_record_ref(self):
        """Auto-populate context and evaluate when record is selected"""
        if self.related_record_ref:
            # Auto-populate context with record data
            self._populate_context_from_record()
            # Auto-evaluate the prompt
            self._auto_evaluate_prompt()
        else:
            # Clear related record metadata from context when record is cleared
            try:
                context = json.loads(self.test_context or "{}")
                # Remove related record metadata
                context.pop('related_model_name', None)
                context.pop('related_model_id', None)
                context.pop('related_res_id', None)
                self.test_context = json.dumps(context, indent=2)
            except (json.JSONDecodeError, Exception):
                pass

    def _auto_evaluate_prompt(self):
        """Auto-evaluate prompt using test method"""
        try:
            # Parse test context
            try:
                user_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError:
                return  # Skip if invalid JSON

            # Use our test method - this uses thread's get_context
            result = self.test_prompt_with_context(user_context)

            # Update wizard fields based on result
            self._update_wizard_from_result(result)

        except Exception as e:
            _logger.debug("Auto-evaluation failed: %s", str(e))
            self.has_error = True
            self.error_message = f"Auto-evaluation error: {str(e)}"

    def _update_wizard_from_result(self, result):
        """Update wizard fields from test result"""
        if result['success']:
            self.has_error = False
            self.error_message = ""
            self.rendered_template = result['rendered_template']

            # Convert messages to different formats
            messages = result['messages']
            self.messages_json = json.dumps(messages, indent=2, ensure_ascii=False)

            # Convert to YAML
            try:
                self.messages_yaml = yaml.dump(messages, default_flow_style=False, allow_unicode=True, indent=2)
            except Exception as e:
                self.messages_yaml = f"Error converting to YAML: {str(e)}"

            # Convert to readable text
            self.messages_text = self._format_messages_as_text(messages)
        else:
            self.has_error = True
            self.error_message = result['error']
            self.rendered_template = ""
            self.messages_json = ""
            self.messages_yaml = ""
            self.messages_text = f"Error during evaluation: {result['error']}"

    def _format_messages_as_text(self, messages):
        """Format messages as readable text"""
        text_parts = []
        for i, message in enumerate(messages, 1):
            role = message.get('role', 'unknown')
            content = message.get('content', '')

            # Extract text content
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].get('text', '')
            elif isinstance(content, str):
                text_content = content
            else:
                text_content = str(content)

            text_parts.append(f"Message {i} ({role.upper()}):\n{text_content}\n")

        return "\n" + "="*50 + "\n".join(text_parts)

    def action_evaluate_prompt(self):
        """Evaluate the prompt using test method"""
        self.ensure_one()

        if not self.prompt_id:
            raise ValidationError(_("No prompt selected"))

        try:
            # Parse test context
            try:
                user_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError as e:
                raise ValidationError(_("Invalid JSON in test context: %s") % str(e))

            # Use our test method - this uses thread's get_context
            result = self.test_prompt_with_context(user_context)

            # Update wizard fields based on result
            self._update_wizard_from_result(result)

        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            self.has_error = True
            self.error_message = str(e)
            self.rendered_template = ""
            self.messages_json = ""
            self.messages_yaml = ""
            self.messages_text = f"Error during evaluation: {str(e)}"
            _logger.exception("Error evaluating prompt %s", self.prompt_id.name)

        # Return an action to keep the wizard open and preserve context
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, keep_context=True),
        }

    def action_reset_context(self):
        """Reset context to defaults using prompt's method"""
        self.ensure_one()
        self.test_context = self._get_default_context()
        self.related_record_ref = False

        # Clear results
        self.rendered_template = ""
        self.messages_json = ""
        self.messages_yaml = ""
        self.messages_text = ""
        self.has_error = False
        self.error_message = ""

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, keep_context=True),
        }

    def action_clear_related_record(self):
        """Clear the related record selection"""
        self.ensure_one()
        self.related_record_ref = False

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, keep_context=True),
        }

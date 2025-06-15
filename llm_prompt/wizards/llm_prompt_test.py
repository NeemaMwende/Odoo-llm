import json
import logging
import yaml
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class RelatedRecordProxy:
    """
    A proxy object that provides clean access to related record fields in Jinja templates.
    Usage in templates: {{ related_record.get_field('field_name', 'default_value') }}
    """

    def __init__(self, record):
        self._record = record

    def get_field(self, field_name, default=""):
        """
        Get a field value from the related record.

        Args:
            field_name (str): The field name to access
            default: Default value if field doesn't exist or is empty

        Returns:
            The field value, or default if not available
        """
        if not self._record:
            return default

        try:
            if hasattr(self._record, field_name):
                value = getattr(self._record, field_name)

                # Handle different field types
                if value is None:
                    return default
                elif isinstance(value, bool):
                    return value  # Keep as boolean for Jinja
                elif hasattr(value, 'name'):  # Many2one field
                    return value.name
                elif hasattr(value, 'mapped'):  # Many2many/One2many field
                    return value.mapped('name')
                else:
                    return value
            else:
                _logger.debug("Field '%s' not found on record %s", field_name, self._record)
                return default

        except Exception as e:
            _logger.error("Error getting field '%s' from record: %s", field_name, str(e))
            return default

    def __getattr__(self, name):
        """Allow direct attribute access as fallback"""
        return self.get_field(name)

    def __bool__(self):
        """Return True if we have a record"""
        return bool(self._record)


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
        """Get default context based on prompt's schema"""
        prompt_id = self.env.context.get('default_prompt_id')
        if not prompt_id:
            return "{}"

        prompt = self.env['llm.prompt'].browse(prompt_id)
        if not prompt.exists():
            return "{}"

        # Generate defaults from schema
        try:
            schema = json.loads(prompt.arguments_json or "{}")
            defaults = {}
            for arg_name, arg_schema in schema.items():
                if 'default' in arg_schema:
                    defaults[arg_name] = arg_schema['default']
                elif arg_schema.get('type') == 'string':
                    defaults[arg_name] = f"sample_{arg_name}"
                elif arg_schema.get('type') == 'number':
                    defaults[arg_name] = 42
                elif arg_schema.get('type') == 'boolean':
                    defaults[arg_name] = True
                elif arg_schema.get('type') == 'array':
                    defaults[arg_name] = ["item1", "item2"]
                else:
                    defaults[arg_name] = f"sample_{arg_name}"

            return json.dumps(defaults, indent=2) if defaults else "{}"
        except (json.JSONDecodeError, Exception):
            return "{}"

    def _create_mock_thread(self):
        """Create a mock context for testing purposes."""
        # Create basic context with simplified related_record access
        context = {
            'thread_id': 'test_thread',
        }

        # Add simplified related_record object
        if self.related_record_ref:
            context['related_record'] = RelatedRecordProxy(self.related_record_ref)
        else:
            context['related_record'] = RelatedRecordProxy(None)  # Empty proxy

        return context

    def action_evaluate_prompt(self):
        """Evaluate the prompt with the given context"""
        self.ensure_one()

        try:
            # Reset error state
            self.has_error = False
            self.error_message = ""

            # Parse test context
            try:
                user_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError as e:
                raise ValidationError(_("Invalid JSON in test context: %s") % str(e))

            # Create enhanced context with simplified related_record access
            enhanced_context = self._create_mock_thread()
            enhanced_context.update(user_context)  # Add user's test context

            # Render the template using the prompt's render method
            try:
                self.rendered_template = self.prompt_id.render(enhanced_context)
            except Exception as e:
                raise ValidationError(_("Error rendering template: %s") % str(e))

            # Generate messages using the prompt's get_messages method
            try:
                messages = self.prompt_id.get_messages(enhanced_context)
            except Exception as e:
                raise ValidationError(_("Error generating messages: %s") % str(e))

            # Convert messages to different formats
            self.messages_json = json.dumps(messages, indent=2, ensure_ascii=False)

            # Convert to YAML
            try:
                self.messages_yaml = yaml.dump(messages, default_flow_style=False, allow_unicode=True, indent=2)
            except Exception as e:
                self.messages_yaml = f"Error converting to YAML: {str(e)}"

            # Convert to readable text
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

            self.messages_text = "\n" + "="*50 + "\n".join(text_parts)

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

        # Return an action to keep the wizard open
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_reset_context(self):
        """Reset context to defaults"""
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
            'context': self.env.context,
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
            'context': self.env.context,
        }

    def action_populate_sample_context(self):
        """Populate context with sample data from the related record"""
        self.ensure_one()

        if not self.related_record_ref:
            raise ValidationError(_("Please select a related record first."))

        try:
            record = self.related_record_ref

            # Parse existing context
            try:
                context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError:
                context = {}

            # Add some common fields from the record as sample data
            sample_fields = ['name', 'display_name', 'email', 'phone', 'mobile',
                             'street', 'city', 'country_id', 'state_id', 'website',
                             'description', 'notes', 'comment']

            for field_name in sample_fields:
                if hasattr(record, field_name):
                    try:
                        value = getattr(record, field_name)
                        if value:
                            # Handle different field types
                            if hasattr(value, 'name'):  # Many2one field
                                context[f"record_{field_name}"] = value.name
                            elif hasattr(value, 'ids'):  # Many2many/One2many field
                                context[f"record_{field_name}"] = [r.name for r in value[:3]]  # Limit to 3
                            else:
                                context[f"record_{field_name}"] = str(value)
                    except Exception:
                        continue

            self.test_context = json.dumps(context, indent=2)

        except Exception as e:
            raise ValidationError(_("Error populating sample context: %s") % str(e))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

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
        _logger.debug("RelatedRecordProxy initialized with record: %s", record)

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
            _logger.debug("No record available, returning default for field '%s'", field_name)
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

    def _populate_context_from_record(self):
        """Populate context with sample data from the related record"""
        if not self.related_record_ref:
            return

        try:
            record = self.related_record_ref
            _logger.info("Auto-populating context from record: %s (ID: %s)", record, record.id)

            # Parse existing context, preserving user data
            try:
                context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError:
                context = {}

            # Add record metadata
            context['related_model_name'] = record._name
            context['related_model_id'] = record._name
            context['related_res_id'] = record.id

            # Add some common fields from the record as sample data
            sample_fields = ['name', 'display_name', 'email', 'phone', 'mobile',
                             'street', 'city', 'country_id', 'state_id', 'website',
                             'description', 'notes', 'comment', 'reference', 'code']

            added_fields = []
            for field_name in sample_fields:
                field_key = f"record_{field_name}"
                # Only add if not already present (preserve user data)
                if field_key not in context and hasattr(record, field_name):
                    try:
                        value = getattr(record, field_name)
                        if value:
                            # Handle different field types
                            if hasattr(value, 'name'):  # Many2one field
                                context[field_key] = value.name
                                added_fields.append(field_key)
                            elif hasattr(value, 'ids'):  # Many2many/One2many field
                                names = [r.name for r in value[:3]]  # Limit to 3
                                if names:
                                    context[field_key] = names
                                    added_fields.append(field_key)
                            else:
                                context[field_key] = str(value)
                                added_fields.append(field_key)
                    except Exception as e:
                        _logger.debug("Could not get field %s: %s", field_name, str(e))
                        continue

            # Add a note about the related_record access (only if not present)
            if '_related_record_help' not in context:
                context['_related_record_help'] = "Use {{ related_record.get_field('field_name') }} in your template to access record fields directly"

            self.test_context = json.dumps(context, indent=2)

            if added_fields:
                _logger.info("Auto-added sample fields: %s", ', '.join(added_fields))

        except Exception as e:
            _logger.exception("Error auto-populating context from record")

    def _create_enhanced_context(self, user_context):
        """
        Create enhanced context for prompt evaluation.

        Args:
            user_context (dict): User-provided test context

        Returns:
            dict: Enhanced context with related_record proxy
        """
        # Start with user context
        enhanced_context = dict(user_context)

        # Add thread-specific context
        enhanced_context['thread_id'] = 'test_thread'

        # Add related_record proxy and metadata
        if self.related_record_ref:
            _logger.info("Creating RelatedRecordProxy with record: %s (ID: %s)",
                         self.related_record_ref, self.related_record_ref.id)
            enhanced_context['related_record'] = RelatedRecordProxy(self.related_record_ref)
            # Ensure metadata is in context
            enhanced_context['related_model_name'] = self.related_record_ref._name
            enhanced_context['related_model_id'] = self.related_record_ref._name
            enhanced_context['related_res_id'] = self.related_record_ref.id
        else:
            _logger.debug("No related record selected, creating empty proxy")
            enhanced_context['related_record'] = RelatedRecordProxy(None)
            enhanced_context['related_model_name'] = None
            enhanced_context['related_model_id'] = None
            enhanced_context['related_res_id'] = None

        return enhanced_context

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
        """Auto-evaluate prompt without showing user messages"""
        try:
            # Parse test context
            try:
                user_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError:
                return  # Skip if invalid JSON

            # Create enhanced context with proper related_record handling
            enhanced_context = self._create_enhanced_context(user_context)

            _logger.info("Auto-evaluation - Enhanced context keys: %s", list(enhanced_context.keys()))

            # Reset error state
            self.has_error = False
            self.error_message = ""

            # Render the template
            try:
                self.rendered_template = self.prompt_id.render(enhanced_context)
            except Exception as e:
                _logger.debug("Auto-evaluation template render error: %s", str(e))
                self.has_error = True
                self.error_message = f"Template render error: {str(e)}"
                return

            # Generate messages
            try:
                messages = self.prompt_id.get_messages(enhanced_context)
            except Exception as e:
                _logger.debug("Auto-evaluation message generation error: %s", str(e))
                self.has_error = True
                self.error_message = f"Message generation error: {str(e)}"
                return

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

        except Exception as e:
            _logger.debug("Auto-evaluation failed: %s", str(e))
            self.has_error = True
            self.error_message = f"Auto-evaluation error: {str(e)}"

    def action_evaluate_prompt(self):
        """Evaluate the prompt with the given context"""
        self.ensure_one()

        try:
            # Parse test context
            try:
                user_context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError as e:
                raise ValidationError(_("Invalid JSON in test context: %s") % str(e))

            # Create enhanced context with proper related_record handling
            enhanced_context = self._create_enhanced_context(user_context)

            _logger.info("Manual evaluation - Enhanced context keys: %s", list(enhanced_context.keys()))

            # Reset error state
            self.has_error = False
            self.error_message = ""

            # Render the template using the prompt's render method
            try:
                self.rendered_template = self.prompt_id.render(enhanced_context)
            except Exception as e:
                _logger.exception("Error rendering template")
                raise ValidationError(_("Error rendering template: %s") % str(e))

            # Generate messages using the prompt's get_messages method
            try:
                messages = self.prompt_id.get_messages(enhanced_context)
            except Exception as e:
                _logger.exception("Error generating messages")
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

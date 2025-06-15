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

    # Related record selection - simplified to just store the info
    related_record_model = fields.Char(
        string="Related Record Model",
        help="Model name for the related record (e.g. 'res.partner')",
    )

    related_record_id = fields.Integer(
        string="Related Record ID",
        help="ID of the related record to use in testing",
    )

    related_record_display = fields.Char(
        string="Related Record",
        compute="_compute_related_record_display",
        help="Display name of the selected related record",
    )

    # Create a mock thread for the component to work with
    mock_thread = fields.Json(
        string="Mock Thread Data",
        compute="_compute_mock_thread",
        help="Mock thread data for the related record component",
    )

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

    @api.depends('related_record_model', 'related_record_id')
    def _compute_related_record_display(self):
        for wizard in self:
            if wizard.related_record_model and wizard.related_record_id:
                try:
                    record = self.env[wizard.related_record_model].browse(wizard.related_record_id)
                    if record.exists():
                        wizard.related_record_display = f"{record.display_name} ({wizard.related_record_model})"
                    else:
                        wizard.related_record_display = f"Record not found: {wizard.related_record_model}({wizard.related_record_id})"
                except Exception as e:
                    wizard.related_record_display = f"Error: {str(e)}"
            else:
                wizard.related_record_display = ""

    @api.depends('related_record_model', 'related_record_id')
    def _compute_mock_thread(self):
        """Create mock thread data for the LLMChatThreadRelatedRecord component"""
        for wizard in self:
            mock_thread = {
                'id': 0,  # Mock thread ID
                'relatedThreadModel': wizard.related_record_model or None,
                'relatedThreadId': wizard.related_record_id or None,
                'relatedThread': bool(wizard.related_record_model and wizard.related_record_id),
            }
            wizard.mock_thread = mock_thread

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

    @api.onchange('related_record_model', 'related_record_id')
    def _onchange_related_record(self):
        """Update context when related record changes"""
        if self.related_record_model and self.related_record_id:
            try:
                record = self.env[self.related_record_model].browse(self.related_record_id)
                if record.exists():
                    # Parse existing context
                    try:
                        context = json.loads(self.test_context or "{}")
                    except json.JSONDecodeError:
                        context = {}

                    # Add related record info to context
                    context['related_record'] = json.dumps({
                        "model": record._name,
                        "id": record.id,
                        "display_name": record.display_name,
                    })

                    self.test_context = json.dumps(context, indent=2)
            except Exception:
                pass

    def action_evaluate_prompt(self):
        """Evaluate the prompt with the given context"""
        self.ensure_one()

        try:
            # Reset error state
            self.has_error = False
            self.error_message = ""

            # Parse test context
            try:
                context = json.loads(self.test_context or "{}")
            except json.JSONDecodeError as e:
                raise ValidationError(_("Invalid JSON in test context: %s") % str(e))

            # Add related record to context if specified
            if self.related_record_model and self.related_record_id:
                try:
                    record = self.env[self.related_record_model].browse(self.related_record_id)
                    if record.exists():
                        context['related_record'] = json.dumps({
                            "model": record._name,
                            "id": record.id,
                            "display_name": record.display_name,
                        })

                        # Create a mock thread context for testing
                        thread_context = {
                            'thread_id': 0,  # Mock thread ID
                            'related_record': context['related_record'],
                        }

                        # Temporarily set context for the prompt evaluation
                        context.update(thread_context)
                except Exception as e:
                    _logger.warning("Error setting up related record context: %s", str(e))

            # Render the template
            self.rendered_template = self.prompt_id.render(context)

            # Generate messages
            messages = self.prompt_id.get_messages(context)

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
                content = self._extract_message_content(message)
                text_parts.append(f"Message {i} ({role.upper()}):\n{content}\n")

            self.messages_text = "\n" + "="*50 + "\n".join(text_parts)

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

    def _extract_message_content(self, message):
        """Extract text content from a message regardless of format"""
        content = message.get("content", "")

        if isinstance(content, list) and len(content) > 0:
            # Handle new format with content array
            return content[0].get("text", "")
        elif isinstance(content, str):
            # Handle old format with direct content string
            return content
        else:
            return str(content)

    def action_reset_context(self):
        """Reset context to defaults"""
        self.ensure_one()
        self.test_context = self._get_default_context()
        self.related_record_model = ""
        self.related_record_id = 0

        # Return an action to keep the wizard open
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def update_related_record(self, model, record_id):
        """Called by the frontend component to update the related record"""
        self.ensure_one()
        self.write({
            'related_record_model': model,
            'related_record_id': record_id,
        })
        self._onchange_related_record()
        return True

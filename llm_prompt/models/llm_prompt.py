import json
import logging
import re
from collections.abc import Iterable

import yaml
from jinja2 import Environment, Undefined

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .arguments_schema import validate_arguments_schema

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


class LLMPrompt(models.Model):
    _name = "llm.prompt"
    _description = "LLM Prompt Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        string="Prompt Name",
        required=True,
        tracking=True,
        help="Unique identifier for the prompt template",
    )
    description = fields.Text(
        string="Description",
        tracking=True,
        help="Human-readable description of the prompt",
    )
    active = fields.Boolean(default=True)

    # Categorization
    category_id = fields.Many2one(
        "llm.prompt.category",
        string="Category",
        tracking=True,
        index=True,
        help="Category for organizing prompts",
    )

    # Tags
    tag_ids = fields.Many2many(
        "llm.prompt.tag",
        "llm_prompt_tag_rel",
        "prompt_id",
        "tag_id",
        string="Tags",
        help="Classify and analyze your prompts",
    )

    # Provider and Publisher relations
    provider_ids = fields.Many2many(
        "llm.provider",
        "llm_prompt_provider_rel",
        "prompt_id",
        "provider_id",
        string="Compatible Providers",
        help="LLM providers that can use this prompt",
    )

    publisher_ids = fields.Many2many(
        "llm.publisher",
        "llm_prompt_publisher_rel",
        "prompt_id",
        "publisher_id",
        string="Compatible Publishers",
        help="LLM publishers whose models work well with this prompt",
    )

    # Template field
    template = fields.Text(
        string="Template",
        required=True,
        help="Prompt template content in the selected format",
        tracking=True,
    )

    # Format selection
    format = fields.Selection(
        [
            ("text", "Text"),
            ("yaml", "YAML"),
            ("json", "JSON"),
        ],
        string="Format",
        default="text",
        required=True,
        tracking=True,
        help="Format of the template content",
    )

    # Arguments JSON field
    arguments_json = fields.Text(
        string="Arguments Schema",
        help="JSON object defining all arguments used in this prompt",
        default="""{}""",
        tracking=True,
    )

    # Computed fields for argument info
    argument_count = fields.Integer(
        compute="_compute_argument_count",
        string="Argument Count",
    )

    undefined_arguments = fields.Char(
        compute="_compute_argument_validation",
        string="Undefined Arguments",
        help="Arguments used in templates but not defined in schema",
    )

    # Usage tracking
    usage_count = fields.Integer(
        string="Usage Count",
        default=0,
        readonly=True,
        help="Number of times this prompt has been used",
    )
    last_used = fields.Datetime(
        string="Last Used",
        readonly=True,
        help="When this prompt was last used",
    )

    input_schema_json = fields.Json(
        string="Input Schema JSON",
        compute="_compute_input_schema_json",
        help="JSON schema for input fields",
        store=True,
    )

    _sql_constraints = [
        ("name_unique", "UNIQUE(name)", "The prompt name must be unique."),
    ]

    @api.depends("arguments_json")
    def _compute_argument_count(self):
        for prompt in self:
            try:
                arguments = json.loads(prompt.arguments_json or "{}")
                prompt.argument_count = len(arguments)
            except json.JSONDecodeError:
                prompt.argument_count = 0

    @api.depends("arguments_json", "template")
    def _compute_argument_validation(self):
        for prompt in self:
            # Get defined arguments
            try:
                arguments = json.loads(prompt.arguments_json or "{}")
                defined_args = set(arguments.keys())
            except json.JSONDecodeError:
                defined_args = set()

            # Extract used arguments from template
            used_args = self._extract_arguments_from_template(prompt.template or "")

            # Find undefined arguments
            undefined_args = [name for name in used_args if name not in defined_args]

            if undefined_args:
                prompt.undefined_arguments = ", ".join(undefined_args)
            else:
                prompt.undefined_arguments = False

    @api.constrains("arguments_json")
    def _validate_arguments_schema(self):
        """Validate arguments JSON against schema"""
        for prompt in self:
            if not prompt.arguments_json:
                continue

            is_valid, error = validate_arguments_schema(prompt.arguments_json)
            if not is_valid:
                raise ValidationError(error)

    @api.constrains("template", "format")
    def _validate_template_format(self):
        """Validate template content matches the selected format"""
        for prompt in self:
            if not prompt.template:
                continue

            try:
                if prompt.format == "json":
                    json.loads(prompt.template)
                elif prompt.format == "yaml":
                    yaml.safe_load_all(prompt.template)
                # Text format doesn't need validation
            except (json.JSONDecodeError, yaml.YAMLError) as e:
                raise ValidationError(
                    _("Invalid %s format in template: %s")
                    % (prompt.format.upper(), str(e))
                ) from e

    def get_prompt_data(self):
        """Returns the prompt data in the MCP format"""
        self.ensure_one()

        # Parse arguments
        try:
            arguments = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError:
            arguments = {}

        # Format arguments for MCP
        formatted_args = []
        for name, schema in arguments.items():
            arg_data = {
                "name": name,
                "description": schema.get("description", ""),
                "required": schema.get("required", False),
            }
            formatted_args.append(arg_data)

        return {
            "name": self.name,
            "description": self.description or "",
            "category": self.category_id.name if self.category_id else "",
            "arguments": formatted_args,
        }

    def create_related_record_proxy(self, record):
        """
        Create a RelatedRecordProxy for a given record.
        This is the canonical method for creating related record proxies.

        Args:
            record: The record to wrap in a proxy (can be None)

        Returns:
            RelatedRecordProxy: Proxy object for template access
        """
        return RelatedRecordProxy(record)

    def create_test_context(self, related_record=None, user_context=None):
        """
        Create a test context similar to what llm.thread would create.
        This mirrors the _get_prompt_context method from llm.thread.

        Args:
            related_record: Record to use as related_record (optional)
            user_context (dict): Additional context from user (optional)

        Returns:
            dict: Context ready for prompt rendering
        """
        context = dict(user_context or {})

        # Add thread-like context (but mark as test)
        context['thread_id'] = 'test_thread'
        context['is_test'] = True

        # Add related_record proxy
        context['related_record'] = self.create_related_record_proxy(related_record)

        # Add metadata about the related record
        if related_record:
            context['related_model_name'] = related_record._name
            context['related_model_id'] = related_record._name
            context['related_res_id'] = related_record.id
        else:
            context['related_model_name'] = None
            context['related_model_id'] = None
            context['related_res_id'] = None

        return context

    def generate_sample_context_from_record(self, record):
        """
        Generate sample context data from a record for testing purposes.

        Args:
            record: The record to extract sample data from

        Returns:
            dict: Sample context data
        """
        if not record:
            return {}

        context = {}

        # Add record metadata
        context['related_model_name'] = record._name
        context['related_model_id'] = record._name
        context['related_res_id'] = record.id

        # Add some common fields from the record as sample data
        sample_fields = ['name', 'display_name', 'email', 'phone', 'mobile',
                         'street', 'city', 'country_id', 'state_id', 'website',
                         'description', 'notes', 'comment', 'reference', 'code']

        for field_name in sample_fields:
            field_key = f"record_{field_name}"
            if hasattr(record, field_name):
                try:
                    value = getattr(record, field_name)
                    if value:
                        # Handle different field types
                        if hasattr(value, 'name'):  # Many2one field
                            context[field_key] = value.name
                        elif hasattr(value, 'ids'):  # Many2many/One2many field
                            names = [r.name for r in value[:3]]  # Limit to 3
                            if names:
                                context[field_key] = names
                        else:
                            context[field_key] = str(value)
                except Exception as e:
                    _logger.debug("Could not get field %s: %s", field_name, str(e))
                    continue

        # Add a help note
        context['_related_record_help'] = "Use {{ related_record.get_field('field_name') }} in your template to access record fields directly"

        return context

    def get_default_test_context(self):
        """
        Get default test context based on prompt's arguments schema.

        Returns:
            dict: Default context for testing
        """
        try:
            schema = json.loads(self.arguments_json or "{}")
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

            return defaults
        except (json.JSONDecodeError, Exception):
            return {}

    def test_prompt(self, related_record=None, user_context=None):
        """
        Test the prompt with given parameters, mirroring real thread execution.

        Args:
            related_record: Record to use as related_record (optional)
            user_context (dict): Additional context from user (optional)

        Returns:
            dict: Result containing rendered_template, messages, and any errors
        """
        try:
            # Create context using the same method as llm.thread
            context = self.create_test_context(related_record, user_context)

            # Render template
            rendered_template = self.render(context)

            # Generate messages
            messages = self.get_messages(context)

            return {
                'success': True,
                'rendered_template': rendered_template,
                'messages': messages,
                'context_used': context,
                'error': None
            }

        except Exception as e:
            _logger.exception("Error testing prompt %s", self.name)
            return {
                'success': False,
                'rendered_template': "",
                'messages': [],
                'context_used': user_context or {},
                'error': str(e)
            }

    def get_messages(self, arguments=None):
        """
        Generate messages for this prompt with the given arguments

        Args:
            arguments (dict): Dictionary of argument values (may include related_record object)

        Returns:
            list: List of messages for this prompt
        """
        self.ensure_one()
        arguments = arguments or {}

        # Fill default values for missing arguments
        arguments = self.sudo()._fill_default_values(arguments)

        # Validate arguments against schema
        self._validate_arguments(arguments)

        # Render the template with arguments
        content = self.render(arguments)

        # Parse template based on format
        try:
            if self.format == "text":
                messages = self._parse_text_messages(content)
            elif self.format == "yaml":
                messages = list(self._parse_dict_messages(yaml.safe_load_all(content)))
            elif self.format == "json":
                messages = list(self._parse_dict_messages(json.loads(content)))
            else:
                raise ValidationError(
                    _("Unsupported template format: %s") % self.format
                )
        except Exception as e:
            _logger.error("Error parsing %s template for prompt %s: %s", self.format, self.name, str(e))
            raise ValidationError(_("Error parsing %s template: %s") % (self.format, str(e)))

        # Update usage statistics (only for non-test contexts)
        if not arguments.get('is_test', False):
            self.sudo().write({
                'usage_count': self.usage_count + 1,
                'last_used': fields.Datetime.now()
            })

        return messages

    def _parse_text_messages(self, content):
        """Parse a simple text template"""
        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": content,
                    }
                ],
            }
        ]

    def _parse_dict_messages(self, data):
        """Parse messages from dict, list, or iterator of dicts recursively"""

        # Handle single dict or iterable of items
        items = data if isinstance(data, Iterable) and not isinstance(data, (str, dict)) else [data]

        for item in items:
            if isinstance(item, dict):
                # Check if this dict has a 'content' key - if so, it's a message
                if "content" in item:
                    msg_type = item.get("type", "user")
                    content = item["content"]

                    # Handle multi-line content
                    if isinstance(content, list):
                        content = "\n".join(str(line) for line in content)

                    yield {
                        "role": msg_type,
                        "content": [
                            {
                                "type": "text",
                                "text": str(content),
                            }
                        ],
                    }
                else:
                    # If no 'content' key, recursively check all values in the dict
                    for value in item.values():
                        if isinstance(value, (dict, list)) or (isinstance(value, Iterable) and not isinstance(value, str)):
                            yield from self._parse_dict_messages(value)

            elif isinstance(item, (list, tuple)) or (isinstance(item, Iterable) and not isinstance(item, str)):
                # If item is iterable (but not string), recurse into it
                yield from self._parse_dict_messages(item)

    def _fill_default_values(self, arguments):
        """
        Fill in default values for missing arguments (excluding related_record)

        Args:
            arguments (dict): Provided argument values

        Returns:
            dict: Arguments with defaults filled in
        """
        result = arguments.copy()

        try:
            schema = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError:
            return result

        # Add default values for missing arguments
        for arg_name, arg_schema in schema.items():
            if arg_name not in result and "default" in arg_schema:
                result[arg_name] = arg_schema["default"]

        return result

    def _validate_arguments(self, arguments):
        """
        Validate provided arguments against the schema

        Args:
            arguments (dict): Dictionary of argument values

        Raises:
            ValidationError: If arguments are invalid
        """
        self.ensure_one()

        try:
            schema = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError:
            _logger.warning(
                "Skipping: Invalid JSON in arguments schema: %s", self.arguments_json
            )
            return

        # Check for required arguments (excluding related_record which is system-provided)
        for arg_name, arg_schema in schema.items():
            if arg_schema.get("required", False) and arg_name not in arguments:
                raise ValidationError(_("Missing required argument: %s") % arg_name)

    @api.model
    def _extract_arguments_from_template(self, template_content):
        """
        Extract argument names from a template string.

        Args:
            template_content (str): The template content to search

        Returns:
            set: Set of argument names found in the template
        """
        if not template_content:
            return set()

        # Find all {{argument}} placeholders
        # Match simple variables: {{variable_name}}
        simple_pattern = r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}"
        simple_matches = re.findall(simple_pattern, template_content)

        # Filter out 'related_record' as it's provided by the system
        filtered_matches = [match for match in simple_matches if match != 'related_record']

        return set(filtered_matches)

    def render(self, context):
        """
        Replace argument placeholders in content with their values using Jinja2.

        Args:
            context (dict): Dictionary of argument values (may include related_record object)

        Returns:
            str: Content with placeholders replaced by values
        """
        # Make a copy of context to avoid modifying the original
        context_copy = dict(context)

        # Process boolean values for JSON compatibility (except related_record)
        processed_args = {}
        for arg_name, arg_value in context_copy.items():
            if arg_name == 'related_record':
                # Keep related_record object as-is for Jinja2
                processed_args[arg_name] = arg_value
            elif isinstance(arg_value, bool):
                # Convert Python True/False to JSON true/false for other values
                processed_args[arg_name] = "true" if arg_value else "false"
            else:
                processed_args[arg_name] = arg_value

        # Create Jinja2 environment
        env = Environment(
            variable_start_string="{{",
            variable_end_string="}}",
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=Undefined,  # Handle missing variables gracefully
        )

        # Create and render the template
        try:
            template = env.from_string(self.template)
            return template.render(**processed_args)
        except Exception as e:
            _logger.error("Error rendering template for prompt %s: %s", self.name, str(e))
            raise ValidationError(_("Error rendering template: %s") % str(e))

    def auto_detect_arguments(self):
        """
        Auto-detect arguments from template and add them to schema

        Returns:
            bool: True if successful
        """
        self.ensure_one()

        # Get existing arguments
        try:
            arguments = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError:
            arguments = {}

        # Extract used arguments from template
        used_args = self._extract_arguments_from_template(self.template or "")

        # Add any missing arguments to schema
        updated = False
        for arg_name in used_args:
            if arg_name not in arguments:
                arguments[arg_name] = {
                    "type": "string",
                    "description": f"Auto-detected argument: {arg_name}",
                    "required": False,
                }
                updated = True

        if updated:
            self.arguments_json = json.dumps(arguments, indent=2)

        return True

    def action_test_prompt(self):
        """
        Test the prompt with the enhanced evaluation wizard

        Returns:
            dict: Action to show enhanced test wizard
        """
        self.ensure_one()

        # Create a wizard record with the prompt pre-filled
        wizard = self.env["llm.prompt.test"].create({
            "prompt_id": self.id,
        })

        return {
            "name": _("Test Prompt: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "llm.prompt.test",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
            "view_id": self.env.ref("llm_prompt.llm_prompt_test_view_form").id,
            "context": {
                "default_prompt_id": self.id,
            },
        }

    @api.depends("template", "arguments_json")
    def _compute_input_schema_json(self):
        """
        Compute a proper JSON schema for input fields based on the template and arguments_json.
        This is used for media generation models to provide a customized input form.
        """
        for prompt in self:
            try:
                # Get arguments from arguments_json
                arguments = json.loads(prompt.arguments_json or "{}")

                prompt.input_schema_json = self._generate_json_schema(arguments)
            except Exception as e:
                _logger.error("Error computing input schema JSON: %s", str(e))
                prompt.input_schema_json = {}

    def _generate_json_schema(self, input_json):
        # Initialize dictionaries and lists for schema components
        properties = {}
        required = []

        # Process each property from the input dictionary
        for prop_name, prop_details in input_json.items():
            # Create a copy of prop_details to avoid modifying the original
            prop_schema = dict(prop_details)

            # Check if the property is required and add to the required list if true
            if prop_schema.get("required", False):
                required.append(prop_name)
                # Remove the required key from the property schema
                prop_schema.pop("required", None)

            # Add the property schema to the properties dictionary
            properties[prop_name] = prop_schema

        # Construct the full JSON schema
        schema = {
            "type": "object",
            "properties": properties,
        }

        # Only add required array if there are required fields
        if required:
            schema["required"] = required

        # Return the schema as a Python dictionary
        return schema

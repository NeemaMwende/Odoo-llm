import json
import logging

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class LLMAssistant(models.Model):
    _name = "llm.assistant"
    _description = "LLM Assistant"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(
        string="Name",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)

    # Assistant configuration
    provider_id = fields.Many2one(
        "llm.provider",
        string="Provider",
        ondelete="restrict",
        tracking=True,
    )
    model_id = fields.Many2one(
        "llm.model",
        string="Model",
        domain="[('provider_id', '=', provider_id), ('model_use', 'in', ['chat', 'multimodal'])]",
        ondelete="restrict",
        tracking=True,
        required=False,
    )

    # Prompt template integration
    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt Template",
        ondelete="restrict",
        tracking=True,
        required=True,
        help="Prompt template to use for generating system prompts",
    )

    # Default values for prompt variables as JSON
    default_values = fields.Text(
        string="Default Values",
        help="JSON object with default values for prompt variables. Can include Python expressions that will be evaluated using safe_eval.",
        default="{}",
        tracking=True,
    )
    
    # Whether default values contain expressions to be evaluated
    has_dynamic_defaults = fields.Boolean(
        string="Has Dynamic Defaults",
        default=False,
        help="Enable if your default values contain Python expressions that should be evaluated",
        tracking=True,
    )
    
    # Evaluated default values (for API)
    evaluated_default_values = fields.Text(
        string="Evaluated Default Values",
        compute="_compute_evaluated_default_values",
        help="Default values with any expressions evaluated",
    )

    # Tools configuration
    tool_ids = fields.Many2many(
        "llm.tool",
        string="Preferred Tools",
        help="Tools that this assistant can use",
        tracking=True,
    )

    # Stats
    thread_count = fields.Integer(
        string="Thread Count",
        compute="_compute_thread_count",
        help="Number of threads using this assistant",
    )
    thread_ids = fields.One2many(
        "llm.thread",
        "assistant_id",
        string="Threads",
        help="Threads using this assistant",
    )

    system_prompt_preview = fields.Text(
        string="System Prompt Preview",
        compute="_compute_system_prompt_preview",
        help="Preview of the formatted system prompt based on the prompt template",
        tracking=True,
    )

    @api.depends("prompt_id", "default_values")
    def _compute_system_prompt_preview(self):
        """Compute preview of the formatted system prompt"""
        for assistant in self:
            assistant.system_prompt_preview = assistant.get_formatted_system_prompt()

    @api.depends('thread_ids')
    def _compute_thread_count(self):
        """Compute the number of threads using this assistant"""
        for assistant in self:
            assistant.thread_count = len(assistant.thread_ids)

    @api.depends('default_values', 'has_dynamic_defaults')
    def _compute_evaluated_default_values(self):
        """Compute the evaluated default values for API use"""
        for assistant in self:
            assistant.evaluated_default_values = assistant.get_evaluated_default_values()

    def action_view_threads(self):
        """Open the threads using this assistant"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "llm_thread.llm_thread_action"
        )
        action["domain"] = [("assistant_id", "=", self.id)]
        action["context"] = {"default_assistant_id": self.id}
        return action

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure default_values is valid JSON"""
        for vals in vals_list:
            if "default_values" in vals and vals["default_values"]:
                try:
                    json.loads(vals["default_values"])
                except json.JSONDecodeError:
                    vals["default_values"] = "{}"
        return super().create(vals_list)

    @api.onchange("prompt_id")
    def _onchange_prompt_id(self):
        """Update default_values when prompt_id changes"""
        if self.prompt_id:
            # Get the prompt arguments schema
            try:
                args_schema = json.loads(self.prompt_id.arguments_json or "{}")
                default_values = {}

                # Extract default values from schema
                for arg_name, arg_schema in args_schema.items():
                    if "default" in arg_schema:
                        default_values[arg_name] = arg_schema["default"]

                # If we have any defaults, update default_values
                if default_values:
                    self.default_values = json.dumps(default_values, indent=2)
            except json.JSONDecodeError:
                pass

    def get_formatted_system_prompt(self, thread=None):
        """Generate a formatted system prompt based on the prompt template
        
        Args:
            thread (llm.thread): Optional thread that is requesting the prompt
                                If provided, it will be added to the context
        
        Returns:
            str: Formatted system prompt
        """
        self.ensure_one()

        if not self.prompt_id:
            return ""
            
        # If we have a thread, add it to the context so our enhanced
        # _substitute_placeholders method can access it
        if thread:
            # Create a context with the thread_id
            context = dict(self.env.context, thread_id=thread.id)
            # Use the prompt with the new context
            return self.with_context(context).prompt_id.get_formatted_system_prompt(
                self.get_evaluated_default_values(thread) or "{}"
            )
        
        return self.prompt_id.get_formatted_system_prompt(
            self.get_evaluated_default_values() or "{}"
        )
        
    def get_evaluated_default_values(self, thread=None):
        """Evaluate default values, processing any Python expressions if has_dynamic_defaults is enabled
        
        Args:
            thread (llm.thread): Optional thread to provide context for evaluation
            
        Returns:
            str: JSON string with evaluated default values
        """
        self.ensure_one()
        
        if not self.default_values:
            return "{}"
            
        try:
            # Parse the default values JSON
            default_values_dict = json.loads(self.default_values)
            
            # If dynamic defaults are enabled, evaluate expressions
            if self.has_dynamic_defaults:
                # Prepare evaluation context
                eval_context = {
                    'env': self.env,
                    'user': self.env.user,
                }
                
                # Add thread-related context if available
                if thread:
                    eval_context.update({
                        'thread': thread,
                        'related_record': thread.get_related_record(),
                    })
                
                # Process each value that might contain an expression
                for key, value in default_values_dict.items():
                    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                        # Extract the expression from ${...}
                        expr = value[2:-1].strip()
                        try:
                            # Evaluate the expression using safe_eval
                            result = safe_eval(expr, eval_context)
                            default_values_dict[key] = result
                        except Exception as e:
                            _logger.warning(f"Error evaluating expression '{expr}': {e}")
                            # Keep the original value on error
                
            # Return the processed values as JSON
            return json.dumps(default_values_dict)
            
        except json.JSONDecodeError as e:
            _logger.error(f"Invalid JSON in default_values: {e}")
            return "{}"
        except Exception as e:
            _logger.error(f"Error processing default_values: {e}")
            return "{}"
            
    def _get_json_fields(self):
        """Return fields that should be serialized as JSON in the API"""
        return ['default_values', 'evaluated_default_values']
